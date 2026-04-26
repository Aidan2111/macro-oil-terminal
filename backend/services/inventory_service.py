"""Inventory service — adapter over the legacy EIA / FRED inventory stack.

Calls ``providers.inventory.fetch_inventory`` + ``quantitative_models
.forecast_depletion`` to produce an :class:`InventoryResponse`.

As with the spread service, caching lives at the router layer — this
module is a pure function of the upstream modules.
"""

from __future__ import annotations

from . import _compat  # noqa: F401

import math
from datetime import timedelta

import pandas as pd

from ..models.inventory import (
    DepletionForecast,
    InventoryPoint,
    InventoryResponse,
)


_DEFAULT_FLOOR_BBLS = 300_000_000.0


def _as_float(value: object) -> float | None:
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def get_inventory_response(
    history_years: int = 2,
    floor_bbls: float = _DEFAULT_FLOOR_BBLS,
) -> InventoryResponse:
    """Fetch inventories + forecast depletion; return a JSON-shaped response."""
    from providers import inventory as inventory_provider  # type: ignore[import-not-found]
    from quantitative_models import forecast_depletion  # type: ignore[import-not-found]

    result = inventory_provider.fetch_inventory()
    frame: pd.DataFrame = result.frame
    if frame is None or frame.empty:
        raise RuntimeError("inventory provider returned empty frame")

    # Trailing 2y window for history (keep the full frame for the forecast
    # — forecast_depletion already controls its own lookback).
    cutoff = pd.Timestamp(frame.index.max()) - timedelta(days=int(history_years) * 365)
    history_frame = frame[frame.index >= cutoff]

    history = [
        InventoryPoint(
            date=pd.Timestamp(idx).date().isoformat(),
            commercial_bbls=_as_float(row.get("Commercial_bbls")),
            spr_bbls=_as_float(row.get("SPR_bbls")),
            cushing_bbls=_as_float(row.get("Cushing_bbls")),
            total_bbls=_as_float(row.get("Total_Inventory_bbls")),
        )
        for idx, row in history_frame.iterrows()
    ]

    latest = frame.iloc[-1]
    as_of = pd.Timestamp(frame.index[-1]).date().isoformat()

    forecast_raw = forecast_depletion(frame, floor_bbls=floor_bbls)
    projected_date = forecast_raw.get("projected_floor_date")
    projected_iso: str | None = None
    if projected_date is not None:
        try:
            projected_iso = pd.Timestamp(projected_date).date().isoformat()
        except Exception:
            projected_iso = None

    forecast = DepletionForecast(
        daily_depletion_bbls=float(forecast_raw.get("daily_depletion_bbls", 0.0)),
        weekly_depletion_bbls=float(forecast_raw.get("weekly_depletion_bbls", 0.0)),
        projected_floor_date=projected_iso,
        r_squared=float(forecast_raw.get("r_squared", 0.0)),
        floor_bbls=float(forecast_raw.get("floor_bbls", floor_bbls)),
    )

    commercial = _as_float(latest.get("Commercial_bbls")) or 0.0
    spr = _as_float(latest.get("SPR_bbls")) or 0.0
    cushing = _as_float(latest.get("Cushing_bbls")) or 0.0
    total = _as_float(latest.get("Total_Inventory_bbls"))
    if total is None:
        total = commercial + spr

    return InventoryResponse(
        commercial_bbls=commercial,
        spr_bbls=spr,
        cushing_bbls=cushing,
        total_bbls=total,
        as_of=as_of,
        source=result.source,
        history=history,
        forecast=forecast,
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
