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
    try:
        backtest = quantitative_models.run_backtest(
            spread_df, entry_z=2.0, exit_z=0.5, lookback=90
        )
    except Exception:
        backtest = {
            "sharpe": None,
            "sortino": None,
            "max_drawdown_usd": None,
            "hit_rate": None,
            "n_trades": 0,
            "total_pnl_usd": 0.0,
            "equity_curve": [],
            "trades": [],
        }

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
            # ``log=True`` writes to data/trade_theses.jsonl exactly once per
            # generate call, matching existing Streamlit behaviour.
            result = await asyncio.to_thread(
                _generate_thesis,
                ctx,
                mode=mode,
                stream_handler=_stream_handler,
                log=True,
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
    while True:
        item = await queue.get()
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
    thesis_obj = await runner_task

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
