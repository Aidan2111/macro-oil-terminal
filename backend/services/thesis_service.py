"""Thesis service — SSE bridge + latest/history readers.

The LLM generator (``trade_thesis.generate_thesis``) is synchronous and
exposes a sync ``stream_handler(delta_text)`` callback. The FastAPI SSE route
is async, so we bridge the two worlds via an ``asyncio.Queue``:

  1. The route spawns ``generate_thesis`` in a worker thread via
     ``asyncio.to_thread``.
  2. The route passes a sync ``stream_handler`` that, on the worker thread,
     calls ``loop.call_soon_threadsafe(queue.put_nowait, chunk)``.
  3. The async generator returning SSE chunks awaits on the queue and yields
     each chunk up to the ASGI transport.

This avoids a custom executor, uses only stdlib asyncio primitives, and keeps
the SSE contract (progress → delta → done) explicit at the route layer.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import pathlib
from typing import Any, AsyncIterator, Optional

from . import _compat  # noqa: F401 — sets sys.path for legacy imports

# Sentinel pushed on the queue to signal the producer finished.
_DONE = object()

# SSE keepalive interval (seconds). Azure App Service's ARR proxy drops
# idle connections; sending a comment line keeps the socket alive during
# the Foundry polling phase where no deltas flow.
_SSE_KEEPALIVE_INTERVAL_S = 15


def _read_recent_theses(limit: int) -> list[dict]:
    """Proxy to ``trade_thesis.read_recent_theses`` with lazy import.

    Re-resolved on every call so tests can monkey-patch
    ``trade_thesis.read_recent_theses`` directly.
    """
    import trade_thesis  # type: ignore

    return trade_thesis.read_recent_theses(limit)


def _build_thesis_context() -> Any:
    """Assemble a real ThesisContext by calling every provider in
    parallel-but-sequential lazy-import order.

    The legacy `thesis_context.build_context()` requires a fairly hefty
    bag of pre-computed artefacts (pricing, inventory, spread frame,
    backtest, depletion, AIS, optional cointegration / crack / CFTC).
    We pull each piece via its provider then hand the bundle off.
    """
    import pandas as pd  # noqa: F401  (chained imports rely on it)

    import thesis_context  # type: ignore
    import quantitative_models  # type: ignore
    from providers import pricing as pricing_provider  # type: ignore
    from providers import inventory as inventory_provider  # type: ignore

    # 1. Pricing — yfinance (Brent + WTI daily).
    pricing_res = pricing_provider.fetch_pricing_daily()

    # 2. Inventory — EIA / FRED.
    try:
        inventory_res = inventory_provider.fetch_inventory()
    except Exception:
        inventory_res = None

    # 3. Spread + Z-score frame.
    spread_df = quantitative_models.compute_spread_zscore(pricing_res.frame)

    # 4. Backtest — keep light, run a fresh tiny pass to seed metrics.
    #    Every numeric key MUST be a float (build_context calls
    #    float(backtest.get(...)) with a 0.0 default — but Python's
    #    `dict.get(key, default)` only returns the default when the key
    #    is absent, NOT when its value is None. Pin all numeric fields
    #    to 0.0 instead of None to dodge `float(None)` TypeErrors.
    try:
        backtest = quantitative_models.run_backtest(
            spread_df, entry_z=2.0, exit_z=0.5, lookback=90
        )
    except Exception:
        backtest = {}
    # Normalise the keys build_context references with float() — coerce
    # None / missing to 0.0 so the legacy zero-defaulting stays sound.
    for k in (
        "win_rate",
        "hit_rate",
        "avg_days_held",
        "avg_pnl_per_bbl",
        "max_drawdown_usd",
        "sharpe",
        "sortino",
        "total_pnl_usd",
    ):
        v = backtest.get(k)
        if v is None:
            backtest[k] = 0.0
        else:
            try:
                backtest[k] = float(v)
            except (TypeError, ValueError):
                backtest[k] = 0.0
    backtest.setdefault("equity_curve", [])
    backtest.setdefault("trades", [])
    backtest.setdefault("n_trades", 0)

    # 5. Depletion forecast on inventory.
    if inventory_res is not None and getattr(inventory_res, "frame", None) is not None:
        try:
            depletion = quantitative_models.forecast_depletion(
                inventory_res.frame, floor_bbls=300_000_000.0
            )
        except Exception:
            depletion = {}
    else:
        depletion = {}

    # 6. AIS — best effort. If AISStream key is set we lean on the
    #    fleet_service producer; otherwise the historical snapshot
    #    keeps the context render-able. fetch_ais_data returns an
    #    AISResult dataclass; build_context expects raw frames.
    try:
        from data_ingestion import fetch_ais_data  # type: ignore

        result = fetch_ais_data(n_vessels=300)
        # AISResult exposes its DataFrame via `.frame` (legacy
        # convention shared with PricingResult / InventoryResult).
        ais_with_cat = (
            getattr(result, "frame", None) if hasattr(result, "frame") else result
        )
        if ais_with_cat is None:
            ais_with_cat = pd.DataFrame()
        ais_agg = ais_with_cat
    except Exception:
        ais_with_cat = pd.DataFrame()
        ais_agg = pd.DataFrame()

    # 7. CFTC — optional, but improves the context. build_context()
    #    reads `cftc_res.mm_zscore_3y` directly, but COTResult is a
    #    plain dataclass without that field; compute it via the
    #    sibling helper and monkey-attach so the legacy path is happy.
    cftc_res = None
    try:
        from providers import _cftc as cftc_provider  # type: ignore

        cftc_res = cftc_provider.fetch_wti_positioning()
        try:
            z = cftc_provider.managed_money_zscore(cftc_res.frame)
            setattr(cftc_res, "mm_zscore_3y", float(z) if z is not None else None)
        except Exception:
            setattr(cftc_res, "mm_zscore_3y", None)
    except Exception:
        cftc_res = None

    # 8. Q3 prediction-quality enrichments — cointegration + regime + GARCH.
    #    All three are best-effort and each has its own defensive
    #    fallback inside the service so a failure here only shows up as
    #    a missing pill in the UI, never a 500 on the SSE path. We keep
    #    the spread frame in scope from step 3.
    coint_info: dict | None = None
    regime_info: dict | None = None
    garch_info: dict | None = None
    try:
        from .cointegration_service import compute_cointegration_for_thesis  # type: ignore
        # Engle-Granger needs Brent + WTI series — pull them off the
        # pricing frame, not the (mean-augmented) spread frame.
        coint_input = pricing_res.frame[["Brent", "WTI"]].copy()
        cs = compute_cointegration_for_thesis(coint_input)
        coint_info = {
            "p_value": cs.eg_pvalue,
            "verdict": cs.verdict,
            "hedge_ratio": cs.hedge_ratio,
            "half_life_days": cs.half_life_days,
        }
    except Exception:
        coint_info = None
    try:
        from .regime_service import detect_regime  # type: ignore
        rs = detect_regime(pricing_res.frame)
        regime_info = rs.to_dict()
    except Exception:
        regime_info = None
    try:
        from .garch_stretch import compute_garch_normalized_stretch  # type: ignore
        gz, gdiag = compute_garch_normalized_stretch(spread_df)
        garch_info = {"z": gz, **gdiag}
    except Exception:
        garch_info = None
    # Issue #77 — Strait of Hormuz tanker transit counter. Read the
    # already-computed envelope from `geopolitical_service` so the
    # thesis context picks up the same numbers the macro tile shows.
    try:
        from . import geopolitical_service  # type: ignore
        env = geopolitical_service.compute_envelope()
        hormuz_info = {
            "transits_24h": int(env.get("count_24h", 0)),
            "transits_pct_1y": float(env.get("percentile_1y", 0.0)),
        }
    except Exception:
        hormuz_info = None
    # Issue #79 — EIA STEO Iran crude production. Best-effort fetch;
    # the LLM sees `iran_production_kbpd` whenever the EIA key is
    # configured and the STEO endpoint is reachable.
    try:
        from . import iran_production_service  # type: ignore
        iran_env = iran_production_service.compute_envelope()
        iran_production_info = {
            "latest_kbpd": float(iran_env.get("latest_kbpd", 0.0)),
        }
    except Exception:
        iran_production_info = None
    # Issue #78 — Iran-flagged + Iran-destined tanker counter.
    try:
        from . import iran_tanker_service  # type: ignore
        tanker_env = iran_tanker_service.compute_envelope()
        iran_tanker_info = {
            "exports_7d": int(tanker_env.get("exports_7d", 0)),
            "imports_7d": int(tanker_env.get("imports_7d", 0)),
        }
    except Exception:
        iran_tanker_info = None
    # Issue #80 — RSS news aggregator + VADER sentiment.
    try:
        from . import news_service  # type: ignore
        from providers import news_rss
        env = news_service.compute_envelope()
        top = news_rss.top_weighted(env.get("headlines", []), limit=5)
        news_info = {"top_headlines": top}
    except Exception:
        news_info = None
    # Issue #81 — OFAC sanctions delta. Best-effort; deltas missing
    # just leave the LLM without that catalyst input rather than failing
    # the whole thesis.
    try:
        from . import ofac_service  # type: ignore
        ofac_env = ofac_service.compute_envelope()
        delta = ofac_env.get("delta_vs_baseline", {}) or {}
        ofac_info = {
            "delta_iran": int(delta.get("iran", 0)),
            "delta_russia": int(delta.get("russia", 0)),
            "delta_venezuela": int(delta.get("venezuela", 0)),
        }
    except Exception:
        ofac_info = None
    # Issue #82 — Russia mirror.
    try:
        from . import russia_service  # type: ignore
        ru_env = russia_service.compute_envelope()
        russia_info = {
            "chokepoint_transits_24h": int(ru_env.get("chokepoint_transits_24h", 0)),
            "percentile_1y": float(ru_env.get("percentile_1y", 0.0)),
            "exports_7d": int(ru_env.get("exports_7d", 0)),
            "imports_7d": int(ru_env.get("imports_7d", 0)),
        }
    except Exception:
        russia_info = None

    return thesis_context.build_context(
        pricing_res=pricing_res,
        inventory_res=inventory_res,
        spread_df=spread_df,
        backtest=backtest,
        depletion=depletion,
        ais_agg=ais_agg,
        ais_with_cat=ais_with_cat,
        z_threshold=2.0,
        floor_bbls=300_000_000.0,
        cftc_res=cftc_res,
        coint_info=coint_info,
        regime_info=regime_info,
        garch_info=garch_info,
        hormuz_info=hormuz_info,
        iran_production_info=iran_production_info,
        iran_tanker_info=iran_tanker_info,
        news_info=news_info,
        ofac_info=ofac_info,
        russia_info=russia_info,
    )


def _generate_thesis(ctx: Any, *, mode: str, stream_handler, log: bool):
    """Lazy import of the LLM generator — simplifies monkey-patching."""
    import trade_thesis  # type: ignore

    return trade_thesis.generate_thesis(
        ctx, mode=mode, stream_handler=stream_handler, log=log
    )


def get_latest_thesis() -> Optional[dict]:
    """Return the most recent audit record, or ``None`` if the log is empty.

    Each record is the dict written by ``trade_thesis._append_audit``:
    ``{timestamp, source, model, context_fingerprint, context, thesis, guardrails}``.
    """
    records = _read_recent_theses(1)
    if not records:
        return None
    return records[0]


def get_thesis_history(limit: int = 30) -> list[dict]:
    """Return up to ``limit`` most-recent audit records, newest first."""
    if limit <= 0:
        return []
    return _read_recent_theses(limit)


def _thesis_to_dict(thesis: Any) -> dict:
    """Serialise a ``trade_thesis.Thesis`` dataclass into a plain dict."""
    if dataclasses.is_dataclass(thesis):
        return dataclasses.asdict(thesis)
    if isinstance(thesis, dict):
        return thesis
    # Defensive fallback — at least return something JSON-serialisable.
    return {"raw": str(thesis)}


async def stream_thesis(
    *,
    mode: str,
    portfolio_usd: int,
    force: bool = False,
    ctx: Any = None,
) -> AsyncIterator[dict]:
    """Yield SSE events for a single thesis-generation run.

    Events:
        ``progress`` — stage + pct, one before context fetch, one before LLM
            call, one before guardrails.
        ``delta`` — ``{"text": <chunk>}`` for each streamed LLM token.
        ``done`` — final ``{thesis, applied_guardrails, materiality_flat}``.

    Each yielded dict has the ``event``/``data`` keys that
    ``sse_starlette.EventSourceResponse`` serialises. ``data`` is pre-JSON-
    encoded so callers don't need to double-encode.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Any] = asyncio.Queue()

    # --- Stage 1: fetching context (cheap, run inline on the event loop) ---
    yield {
        "event": "progress",
        "data": json.dumps({"stage": "fetching_context", "pct": 10}),
    }
    if ctx is None:
        # build_thesis_context() is potentially slow + network-bound — but
        # here we run it in a thread so the event loop isn't blocked. If it
        # fails, surface a proper error event rather than a 500.
        try:
            ctx = await asyncio.to_thread(_build_thesis_context)
        except Exception as exc:  # pragma: no cover — depends on upstream wiring
            yield {
                "event": "error",
                "data": json.dumps({"stage": "fetching_context", "error": repr(exc)}),
            }
            return

    # --- Stage 2: calling LLM ---
    yield {
        "event": "progress",
        "data": json.dumps({"stage": "calling_llm", "pct": 40}),
    }

    def _stream_handler(chunk: str) -> None:
        """Sync callback invoked from the worker thread by trade_thesis."""
        # asyncio.Queue is not itself thread-safe for coroutine scheduling;
        # call_soon_threadsafe marshals into the loop thread cleanly.
        loop.call_soon_threadsafe(queue.put_nowait, chunk)

    async def _runner() -> Any:
        try:
            # ``log=False`` here — we defer the audit-log write to AFTER
            # ``decorate_thesis_for_execution`` runs below, so the
            # persisted record contains the decorated `instruments` and
            # `checklist` arrays the frontend needs on first paint.
            # The runner used to write the audit row inline (with
            # ``log=True``), but that captured the undecorated thesis
            # and `/api/thesis/latest` then returned a record with
            # empty instruments / empty checklist — the visible bug
            # behind the "Today's read is messed up" report.
            result = await asyncio.to_thread(
                _generate_thesis,
                ctx,
                mode=mode,
                stream_handler=_stream_handler,
                log=False,
            )
            return result
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _DONE)

    # Intentionally unused but referenced to silence linters on ``force`` / ``portfolio_usd``;
    # both are captured on the thesis record via the audit log so downstream
    # UIs can render portfolio sizing without the backend persisting it here.
    _ = (portfolio_usd, force)

    runner_task = asyncio.create_task(_runner())

    # --- Stage 3: stream deltas as they arrive ---
    # The Foundry path is poll-based and emits a single bulk delta only
    # after the run completes (60-240s). During that silence the Azure
    # App Service ARR proxy can kill the idle connection. We use
    # asyncio.wait_for with a short timeout and yield SSE comment lines
    # (`: keepalive`) to keep the socket alive.
    while True:
        try:
            item = await asyncio.wait_for(
                queue.get(), timeout=_SSE_KEEPALIVE_INTERVAL_S
            )
        except asyncio.TimeoutError:
            yield {"event": "keepalive"}
            continue
        if item is _DONE:
            break
        yield {
            "event": "delta",
            "data": json.dumps({"text": item}),
        }

    # --- Stage 4: guardrails + done ---
    yield {
        "event": "progress",
        "data": json.dumps({"stage": "applying_guardrails", "pct": 90}),
    }

    # await the runner so we surface any exception from the worker thread.
    # If the runner raised (e.g. FoundryRunError on a deadline trip), wrap
    # it as an `event: error` SSE frame instead of letting the exception
    # bubble up and truncate the stream silently. Without this, the user-
    # visible symptom is "progress went 10/40/90 then nothing" — same
    # symptom we hit on the 2026-04-26 USE_FOUNDRY=true retry.
    try:
        thesis_obj = await runner_task
    except Exception as exc:  # pragma: no cover — exercised in production
        yield {
            "event": "error",
            "data": json.dumps(
                {
                    "stage": "generate",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            ),
        }
        return

    # Populate .instruments and .checklist — the decorator is a pure function
    # that returns a deepcopy; ctx is guaranteed non-None at this point.
    import trade_thesis as _tt  # type: ignore
    thesis_obj = _tt.decorate_thesis_for_execution(thesis_obj, ctx)

    # Persist the decorated thesis — _generate_thesis was invoked with
    # log=False so we own the audit-log write here. Wrapped so any
    # disk failure is logged but never breaks the SSE response.
    try:
        _tt._append_audit(ctx, thesis_obj)
    except Exception:  # pragma: no cover — audit-log writes never fatal
        import logging as _audit_logging
        _audit_logging.getLogger(__name__).debug(
            "audit append failed (post-decoration)", exc_info=True
        )

    applied_guardrails = list(getattr(thesis_obj, "guardrails_applied", []) or [])
    raw = _thesis_to_dict(thesis_obj)
    stance = str(raw.get("raw", {}).get("stance") or raw.get("stance") or "") \
        if isinstance(raw, dict) else ""
    materiality_flat = stance == "flat"

    yield {
        "event": "done",
        "data": json.dumps(
            {
                "thesis": raw,
                "applied_guardrails": applied_guardrails,
                "materiality_flat": materiality_flat,
            },
            default=str,
        ),
    }


__all__ = [
    "get_latest_thesis",
    "get_thesis_history",
    "stream_thesis",
]


# ---------------------------------------------------------------------------
# Q1-DATA-QUALITY-LAST-FETCH-STATE
# Tiny in-memory snapshot of the last successful fetch. Exposed so
# backend.services.data_quality can build a /api/data-quality envelope
# without reaching across legacy provider internals.
# ---------------------------------------------------------------------------

import threading as _dq_threading
from datetime import datetime as _dq_datetime, timezone as _dq_timezone

_DQ_STATE_LOCK = _dq_threading.Lock()
_DQ_LAST_FETCH: dict[str, object] = {
    "last_good_at": None,   # datetime | None — UTC
    "n_obs": None,          # int | None
    "latency_ms": None,     # int | None
    "message": None,        # str | None — populated on guard violation
    "status": "amber",      # "green" | "amber" | "red"
}


def record_fetch_success(*, n_obs: int | None, latency_ms: int | None,
                          message: str | None = None,
                          degraded: bool = False) -> None:
    """Mark a successful fetch (or degraded/amber if a sanity guard tripped)."""
    with _DQ_STATE_LOCK:
        _DQ_LAST_FETCH["last_good_at"] = _dq_datetime.now(_dq_timezone.utc)
        _DQ_LAST_FETCH["n_obs"] = n_obs
        _DQ_LAST_FETCH["latency_ms"] = latency_ms
        _DQ_LAST_FETCH["message"] = message
        _DQ_LAST_FETCH["status"] = "amber" if degraded else "green"


def record_fetch_failure(message: str) -> None:
    with _DQ_STATE_LOCK:
        _DQ_LAST_FETCH["status"] = "red"
        _DQ_LAST_FETCH["message"] = message


def get_last_fetch_state() -> dict[str, object]:
    """Return a snapshot dict (caller-owned copy)."""
    with _DQ_STATE_LOCK:
        return dict(_DQ_LAST_FETCH)


# ---------------------------------------------------------------------------
# Q1-DATA-QUALITY-WIRING — wrapper that records fetch state when thesis
# records are read from the audit log.
# ---------------------------------------------------------------------------

import time as _dq_time
import logging as _dq_logging

_dq_log = _dq_logging.getLogger(__name__)

_real_get_latest_thesis = get_latest_thesis


def get_latest_thesis() -> Optional[dict]:  # type: ignore[no-redef]
    t0 = _dq_time.monotonic()
    try:
        rec = _real_get_latest_thesis()
    except Exception as exc:
        record_fetch_failure(f"Thesis audit log read failed: {type(exc).__name__}: {exc}")
        raise
    latency_ms = int((_dq_time.monotonic() - t0) * 1000.0)
    n_obs = 1 if rec is not None else 0
    record_fetch_success(n_obs=n_obs, latency_ms=latency_ms)
    return rec
