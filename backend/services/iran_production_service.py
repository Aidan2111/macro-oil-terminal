"""Iran crude oil production via EIA STEO (issue #79).

Wraps `providers._eia.fetch_steo_series("COPR_IR")` and computes the
display payload that `/api/inventory/iran-production` returns:

  {
    series_id: "COPR_IR",
    monthly:   [{month, kbpd}, ...],   # last 24 months, ascending
    latest_kbpd: float,
    ytd_avg_kbpd: float,
    delta_vs_ytd_avg_kbpd: float,
  }

Also wires standard `record_fetch_*` / `get_last_fetch_state` so this
provider lights up in `/api/data-quality` alongside yfinance / EIA /
CFTC / etc.
"""

from __future__ import annotations

import logging
import threading
import time as _time
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# --- Constants --------------------------------------------------------------

# EIA STEO series ID for Iran crude oil production (thousand bbl/day, monthly).
SERIES_IRAN_PRODUCTION = "COPR_IR"

# Window used for the historical-trend display.
DEFAULT_TRAILING_MONTHS = 24


# --- Data-quality wiring ---------------------------------------------------

_DQ_LAST_FETCH: dict[str, object] = {
    "last_good_at": None,
    "n_obs": None,
    "latency_ms": None,
    "message": None,
    "status": "amber",
}
_DQ_STATE_LOCK = threading.Lock()


def get_last_fetch_state() -> dict[str, object]:
    with _DQ_STATE_LOCK:
        return dict(_DQ_LAST_FETCH)


def record_fetch_success(
    *,
    n_obs: Optional[int],
    latency_ms: Optional[int] = None,
    message: Optional[str] = None,
) -> None:
    with _DQ_STATE_LOCK:
        _DQ_LAST_FETCH.update(
            {
                "last_good_at": datetime.now(timezone.utc),
                "n_obs": n_obs,
                "latency_ms": latency_ms,
                "message": message,
                "status": "green",
            }
        )


def record_fetch_failure(message: str) -> None:
    with _DQ_STATE_LOCK:
        _DQ_LAST_FETCH.update({"message": message, "status": "red"})


# --- Fetch + envelope -------------------------------------------------------


def _ytd_avg(rows: list[dict[str, Any]], *, value_key: str = "kbpd") -> float:
    """Average of all rows whose month falls in the latest year present.

    `value_key` defaults to "kbpd" (the post-flatten shape used by
    `compute_envelope`); pass "value" when feeding raw STEO rows.
    """
    if not rows:
        return 0.0
    latest_year = str(rows[-1].get("month", ""))[:4]
    if not latest_year:
        return 0.0
    ytd = [
        float(r[value_key])
        for r in rows
        if str(r.get("month", "")).startswith(latest_year) and value_key in r
    ]
    if not ytd:
        return 0.0
    return sum(ytd) / len(ytd)


def compute_envelope(
    *,
    trailing_months: int = DEFAULT_TRAILING_MONTHS,
    fetch_fn=None,
) -> dict[str, Any]:
    """Pull the STEO Iran production series and shape it for the API.

    `fetch_fn` is injectable for tests — defaults to
    `providers._eia.fetch_steo_series`.
    """
    if fetch_fn is None:
        from providers import _eia

        fetch_fn = _eia.fetch_steo_series

    t0 = _time.monotonic()
    try:
        rows = fetch_fn(SERIES_IRAN_PRODUCTION, limit=trailing_months)
    except Exception as exc:
        record_fetch_failure(
            f"Iran production fetch failed: {type(exc).__name__}: {exc}"
        )
        raise

    monthly = [
        {"month": str(r["month"]), "kbpd": round(float(r["value"]), 3)}
        for r in rows
    ]
    latest_kbpd = float(monthly[-1]["kbpd"]) if monthly else 0.0
    ytd_avg_kbpd = round(_ytd_avg(monthly), 3) if monthly else 0.0
    delta_vs_ytd_avg_kbpd = (
        round(latest_kbpd - ytd_avg_kbpd, 3) if monthly else 0.0
    )

    latency_ms = int((_time.monotonic() - t0) * 1000.0)
    record_fetch_success(n_obs=len(monthly), latency_ms=latency_ms)
    return {
        "series_id": SERIES_IRAN_PRODUCTION,
        "monthly": monthly,
        "latest_kbpd": latest_kbpd,
        "ytd_avg_kbpd": ytd_avg_kbpd,
        "delta_vs_ytd_avg_kbpd": delta_vs_ytd_avg_kbpd,
    }
