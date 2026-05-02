"""Spread service — adapter over the legacy Brent/WTI pricing stack.

Calls ``providers.pricing.fetch_pricing_daily`` + ``quantitative_models
.compute_spread_zscore`` + ``language.describe_stretch`` to produce a
JSON-ready :class:`backend.models.spread.SpreadResponse`.

Kept deliberately thin: no caching here — caching lives at the router
layer (FastAPI dependency with a module-level TTL dict) so the service
stays trivially testable via ``monkeypatch``.
"""

from __future__ import annotations

from . import _compat  # noqa: F401  (must precede legacy imports)

import math

import pandas as pd

from ..models.spread import CorroborationSnapshot, SpreadPoint, SpreadResponse


# Issue #97 — divergence threshold above which the data-quality
# envelope flips yfinance to amber. 2% is the threshold cited in the
# issue body. Live (next-day) FRED vs intraday yfinance commonly
# diverges 0.1-0.3%; ~2% is a genuine "the two feeds disagree"
# signal.
PRICE_CORROBORATION_THRESHOLD = 0.02


def _pair_relative_delta(
    a: dict[str, float | None], b: dict[str, float | None],
) -> float | None:
    """Worst |a-b|/|b| across the brent/wti legs of two providers."""
    deltas: list[float] = []
    for leg in ("brent", "wti"):
        x = a.get(leg)
        y = b.get(leg)
        if x is None or y is None or y == 0.0:
            continue
        deltas.append(abs(x - y) / abs(y))
    if not deltas:
        return None
    return max(deltas)


def _max_relative_delta(yf: dict[str, float | None], fred: dict[str, float | None]) -> float | None:
    """Backwards-compat alias kept for older callers (#97 only checked
    yfinance vs FRED). Issue #106 extends to a 3-source pairwise
    matrix via :func:`_pairwise_max_delta`.
    """
    return _pair_relative_delta(yf, fred)


def _pairwise_max_delta(
    snapshots: dict[str, dict[str, float | None]],
) -> float | None:
    """Worst pairwise relative delta across an arbitrary set of
    provider snapshots (issue #106). Each value is a {brent, wti}
    dict. Pairs with at least one missing leg are skipped silently."""
    keys = [k for k in snapshots if snapshots[k]]
    deltas: list[float] = []
    for i, k1 in enumerate(keys):
        for k2 in keys[i + 1 :]:
            d = _pair_relative_delta(snapshots[k1], snapshots[k2])
            if d is not None:
                deltas.append(d)
    if not deltas:
        return None
    return max(deltas)


def _fetch_twelve_data_latest() -> dict[str, float | None]:
    """Best-effort — returns the latest Twelve Data Brent + WTI close,
    or {brent: None, wti: None} when unkeyed / unreachable."""
    try:
        from providers import _twelvedata

        df = _twelvedata.fetch_daily(years=1)
        if df is None or df.empty:
            return {"brent": None, "wti": None}
        last = df.iloc[-1]
        return {
            "brent": float(last["Brent"]) if "Brent" in last.index else None,
            "wti": float(last["WTI"]) if "WTI" in last.index else None,
        }
    except Exception:
        return {"brent": None, "wti": None}


def corroborate_with_fred(
    *, brent_yf: float | None, wti_yf: float | None,
    fetch_fn=None,
    twelve_data_fn=None,
) -> tuple[CorroborationSnapshot, bool, str | None]:
    """Build a CorroborationSnapshot from yfinance + FRED + Twelve Data.

    Returns ``(snapshot, degraded, message)``. ``degraded`` is True
    iff the worst pairwise relative delta across ANY two sources
    exceeds PRICE_CORROBORATION_THRESHOLD (issue #106 generalises
    issue #97's 2-source check to 3-source).

    Both ``fetch_fn`` (FRED) and ``twelve_data_fn`` (Twelve Data) are
    injectable for tests; default to the live providers. Twelve Data
    is best-effort — when unkeyed it returns all-None and the snapshot
    simply omits it from the pairwise comparison.
    """
    if fetch_fn is None:
        from providers import _fred

        fetch_fn = _fred.fetch_oil_prices_latest
    if twelve_data_fn is None:
        twelve_data_fn = _fetch_twelve_data_latest

    yf = {"brent": brent_yf, "wti": wti_yf}
    try:
        fred = fetch_fn() or {"brent": None, "wti": None}
    except Exception:
        fred = {"brent": None, "wti": None}
    try:
        twelve = twelve_data_fn() or {"brent": None, "wti": None}
    except Exception:
        twelve = {"brent": None, "wti": None}

    snapshots: dict[str, dict[str, float | None]] = {"yfinance": yf}
    if any(v is not None for v in fred.values()):
        snapshots["fred"] = fred
    if any(v is not None for v in twelve.values()):
        snapshots["twelve_data"] = twelve

    delta = _pairwise_max_delta(snapshots)
    snapshot = CorroborationSnapshot(
        yfinance=yf, fred=fred, twelve_data=twelve, max_relative_delta=delta,
    )
    if delta is not None and delta > PRICE_CORROBORATION_THRESHOLD:
        # Identify the worst-pair so the message names the offenders.
        worst_pair = ""
        worst_value = -1.0
        keys = list(snapshots.keys())
        for i, k1 in enumerate(keys):
            for k2 in keys[i + 1 :]:
                d = _pair_relative_delta(snapshots[k1], snapshots[k2])
                if d is not None and d > worst_value:
                    worst_value = d
                    worst_pair = f"{k1} vs {k2}"
        msg = f"price-source divergence: {delta:.3f} ({worst_pair})"
        return snapshot, True, msg
    return snapshot, False, None


def _as_float(value: object) -> float | None:
    """Coerce a pandas/numpy scalar to ``float`` or ``None`` for NaN."""
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def get_spread_response(history_bars: int = 90) -> SpreadResponse:
    """Fetch daily Brent/WTI and return the shaped response model.

    Parameters
    ----------
    history_bars
        Number of trailing daily bars to include in ``history``. Defaults
        to 90, matching the rolling-Z window.
    """
    # Legacy module lookups go through _compat's sys.path injection.
    from providers import pricing  # type: ignore[import-not-found]
    from quantitative_models import compute_spread_zscore  # type: ignore[import-not-found]
    from language import describe_stretch  # type: ignore[import-not-found]

    result = pricing.fetch_pricing_daily()
    zframe: pd.DataFrame = compute_spread_zscore(result.frame)

    if zframe is None or zframe.empty:
        raise RuntimeError("compute_spread_zscore returned empty frame")

    tail = zframe.tail(history_bars)
    latest = zframe.iloc[-1]

    history = [
        SpreadPoint(
            date=pd.Timestamp(idx).date().isoformat(),
            brent=_as_float(row.get("Brent")),
            wti=_as_float(row.get("WTI")),
            spread=_as_float(row.get("Spread")),
            z_score=_as_float(row.get("Z_Score")),
        )
        for idx, row in tail.iterrows()
    ]

    brent_latest = _as_float(latest.get("Brent"))
    wti_latest = _as_float(latest.get("WTI"))
    spread_latest = _as_float(latest.get("Spread"))
    stretch = _as_float(latest.get("Z_Score"))

    if brent_latest is None or wti_latest is None or spread_latest is None:
        raise RuntimeError("latest bar has NaN Brent/WTI/Spread")

    band = describe_stretch(stretch if stretch is not None else 0.0)
    as_of = pd.Timestamp(zframe.index[-1]).date().isoformat()

    return SpreadResponse(
        brent=brent_latest,
        wti=wti_latest,
        spread=spread_latest,
        stretch=stretch,
        stretch_band=band,
        as_of=as_of,
        source=result.source,
        history=history,
    )


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
# Q1-DATA-QUALITY-LINEAGE
# Wrap the legacy `get_spread_response` so each successful call records
# last-fetch state for /api/data-quality. Failures bubble up untouched
# so the existing 503 envelope still fires.
# ---------------------------------------------------------------------------

import time as _dq_time
import logging as _dq_logging

_dq_log = _dq_logging.getLogger(__name__)

_real_get_spread_response = get_spread_response


def get_spread_response(history_bars: int = 90):  # type: ignore[no-redef]
    t0 = _dq_time.monotonic()
    try:
        resp = _real_get_spread_response(history_bars=history_bars)
    except Exception as exc:
        record_fetch_failure(f"yfinance fetch failed: {type(exc).__name__}: {exc}")
        raise
    latency_ms = int((_dq_time.monotonic() - t0) * 1000.0)
    n_obs = len(resp.history) if getattr(resp, "history", None) else None
    degraded = False
    msg = None
    try:
        from backend.services.data_quality import GuardViolation, guard_yfinance_frame
        # Guard runs against a tiny synthetic frame built from the
        # response history so we don't double-fetch yfinance.
        import pandas as _dq_pd
        if resp.history:
            frame = _dq_pd.DataFrame(
                [{"Close": p.spread, "Brent": p.brent, "WTI": p.wti} for p in resp.history]
            )
            try:
                guard_yfinance_frame(frame)
            except GuardViolation as gv:
                degraded = True
                msg = str(gv)
                _dq_log.warning("yfinance guard tripped: %s", gv)
    except Exception:
        # Guard is best-effort — never fail the request because of it.
        pass

    # Issue #97 — cross-source price corroboration vs FRED. Best-effort:
    # if FRED is unavailable or unkeyed, ``corroborate_with_fred`` returns
    # an "all-None FRED" snapshot with delta=None and the wrapper proceeds
    # without flipping data-quality.
    try:
        snap, corroboration_degraded, corroboration_msg = corroborate_with_fred(
            brent_yf=resp.brent, wti_yf=resp.wti
        )
        # Attach the snapshot to the response model so /api/spread
        # callers can read it. Pydantic is OK with assigning to an
        # Optional[Model] field after construction.
        try:
            resp = resp.model_copy(update={"corroboration": snap})
        except Exception:
            # If model_copy isn't available (older pydantic), set on
            # the instance directly — best-effort.
            try:
                resp.corroboration = snap  # type: ignore[attr-defined]
            except Exception:
                pass
        if corroboration_degraded and not degraded:
            degraded = True
            msg = corroboration_msg
            _dq_log.warning("price corroboration tripped: %s", corroboration_msg)
    except Exception as exc:
        _dq_log.warning("corroboration step failed (non-fatal): %s", exc)

    record_fetch_success(n_obs=n_obs, latency_ms=latency_ms,
                         message=msg, degraded=degraded)
    return resp
