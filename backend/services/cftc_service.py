"""CFTC service — adapter over ``providers._cftc``.

Calls ``fetch_wti_positioning`` + ``managed_money_zscore`` and shapes
the weekly COT frame into a :class:`CFTCResponse`.
"""

from __future__ import annotations

from . import _compat  # noqa: F401

import pandas as pd

from ..models.cftc import CFTCPoint, CFTCResponse


def _as_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def get_cftc_response() -> CFTCResponse:
    """Fetch ~3y of WTI positioning + latest snapshot."""
    from providers import _cftc  # type: ignore[import-not-found]

    result = _cftc.fetch_wti_positioning()
    frame: pd.DataFrame = result.frame
    if frame is None or frame.empty:
        raise RuntimeError("CFTC provider returned empty frame")

    history = [
        CFTCPoint(
            date=pd.Timestamp(idx).date().isoformat(),
            mm_net=_as_int(row.get("mm_net")),
            producer_net=_as_int(row.get("producer_net")),
            swap_net=_as_int(row.get("swap_net")),
            open_interest=_as_int(row.get("open_interest")),
        )
        for idx, row in frame.iterrows()
    ]

    latest = frame.iloc[-1]
    mm_net = _as_int(latest.get("mm_net")) or 0
    producer_net = _as_int(latest.get("producer_net")) or 0
    swap_net = _as_int(latest.get("swap_net")) or 0
    commercial_net = producer_net + swap_net

    z = _cftc.managed_money_zscore(frame)
    mm_z = float(z) if z is not None else None

    as_of = pd.Timestamp(frame.index[-1]).date().isoformat()

    return CFTCResponse(
        mm_net=mm_net,
        commercial_net=commercial_net,
        mm_zscore_3y=mm_z,
        as_of=as_of,
        market=str(latest.get("market") or result.market_name or ""),
        source_url=result.source_url,
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
