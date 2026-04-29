"""Geopolitical signals — Strait of Hormuz tanker transit counter.

Counts crude / oil-product tanker transits through a 50nm radius around
the Strait of Hormuz center (~26.5°N, 56.3°E) over rolling 24h windows,
plus a 30-day daily trend and a percentile vs the 30-day distribution.

The data source is the existing AISStream feed (`fleet_service`). This
module adds:

  * `is_in_hormuz_fence(lat, lon)` — haversine geofence helper.
  * `count_24h_transits()` — current ring-buffer vessels inside the fence.
  * `record_daily_count()` — append today's count to the persistent
    per-day bucket on disk (`data/geopolitical/hormuz_daily.jsonl`).
  * `compute_envelope()` — bundle the count, percentile, and 30-day
    trend into the shape `/api/geopolitical/hormuz` returns.
  * `record_fetch_success()` / `record_fetch_failure()` — wired into the
    `data_quality` envelope so `/api/data-quality` lists `hormuz` as a
    provider row alongside yfinance / EIA / CFTC / etc.

Because AIS-based transit counts are inherently noisy and the feed in
production currently returns ~0 messages, the percentile is computed
against the 30-day rolling daily-bucket distribution (degrades to 0
when no history yet) — a 1-year baseline accumulates as the system
ages. Tests cover the geofence math + the percentile formula.
"""

from __future__ import annotations

import json
import logging
import math
import pathlib
import threading
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# --- Geofence constants -----------------------------------------------------

# Strait of Hormuz center — between Bandar Abbas (Iran) and Khasab (Oman).
HORMUZ_CENTER_LAT = 26.5
HORMUZ_CENTER_LON = 56.3
HORMUZ_RADIUS_NM = 50.0  # nautical miles

# Earth radius in nautical miles. 1 nm = 1852 m.
_EARTH_RADIUS_NM = 6371000.0 / 1852.0


def is_in_hormuz_fence(
    lat: float,
    lon: float,
    *,
    center_lat: float = HORMUZ_CENTER_LAT,
    center_lon: float = HORMUZ_CENTER_LON,
    radius_nm: float = HORMUZ_RADIUS_NM,
) -> bool:
    """Return True if (lat, lon) is within `radius_nm` of the center.

    Standard haversine formula. Inputs must be decimal degrees; non-finite
    values return False (defensive against AIS feed quirks where some
    vessels emit (0.0, 0.0) as a placeholder).
    """
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return False
    if not (math.isfinite(lat_f) and math.isfinite(lon_f)):
        return False
    if lat_f == 0.0 and lon_f == 0.0:
        return False  # AIS placeholder, never inside the strait

    phi1 = math.radians(center_lat)
    phi2 = math.radians(lat_f)
    dphi = math.radians(lat_f - center_lat)
    dlambda = math.radians(lon_f - center_lon)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return _EARTH_RADIUS_NM * c <= radius_nm


# --- Daily-bucket persistence ----------------------------------------------

_BUCKET_PATH = pathlib.Path("data/geopolitical/hormuz_daily.jsonl")
_BUCKET_LOCK = threading.Lock()


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _read_buckets() -> list[dict[str, Any]]:
    """Read the daily-bucket history from disk. Empty if file missing."""
    if not _BUCKET_PATH.exists():
        return []
    try:
        rows = []
        for line in _BUCKET_PATH.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # skip corrupt rows
        return rows
    except Exception:
        return []


def record_daily_count(count: int, *, today: Optional[str] = None) -> None:
    """Persist today's transit count to the daily-bucket history.

    Idempotent: if today already has a row, overwrite with the new
    (higher-water-mark) count. Caller decides cadence — typical use is
    to call this every time `count_24h_transits` runs.
    """
    today = today or _today_iso()
    _BUCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _BUCKET_LOCK:
        rows = _read_buckets()
        # Replace existing today row, or append.
        replaced = False
        for r in rows:
            if r.get("date") == today:
                r["count"] = max(int(r.get("count", 0)), int(count))
                replaced = True
                break
        if not replaced:
            rows.append({"date": today, "count": int(count)})
        # Trim to 1 year to bound disk growth.
        rows.sort(key=lambda r: r.get("date", ""))
        if len(rows) > 366:
            rows = rows[-366:]
        _BUCKET_PATH.write_text(
            "\n".join(json.dumps(r) for r in rows) + "\n"
        )


def trend_30d() -> list[dict[str, Any]]:
    """Return the last 30 daily-bucket entries (oldest → newest).

    Each entry is `{"date": "YYYY-MM-DD", "count": int}`. Missing days
    are filled with zero so the frontend sparkline has a stable shape.
    """
    rows = _read_buckets()
    by_date = {r.get("date"): int(r.get("count", 0)) for r in rows if r.get("date")}
    today = datetime.now(timezone.utc).date()
    out: list[dict[str, Any]] = []
    for i in range(29, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        out.append({"date": d, "count": by_date.get(d, 0)})
    return out


# --- Live counts ------------------------------------------------------------


def count_24h_transits() -> int:
    """Count distinct MMSIs currently in the AIS ring-buffer that fall
    within the Hormuz fence and were seen within the last 24 hours.

    This reads `fleet_service._latest_by_mmsi` directly. Vessels that
    haven't been re-emitted in 24h fall out (the AIS feed re-emits
    moving tankers every ~3-15 min, so any vessel actually transiting
    will be present).
    """
    from . import fleet_service  # local import to avoid cycles

    cutoff = _time.time() - 24 * 3600
    count = 0
    for mmsi, vessel in fleet_service._latest_by_mmsi.items():
        ts = vessel.get("_ingested_at")
        if isinstance(ts, (int, float)) and ts < cutoff:
            continue
        lat = vessel.get("Latitude")
        lon = vessel.get("Longitude")
        if lat is None or lon is None:
            continue
        if is_in_hormuz_fence(float(lat), float(lon)):
            count += 1
    return count


def percentile_vs_history(count: int) -> float:
    """Return the percentile (0-100) of `count` against the 30-day
    daily-bucket history. Empty history returns 50 (neutral).

    A higher percentile means the current 24h flow is unusually heavy
    vs the recent rolling-30d distribution.
    """
    history = [int(r.get("count", 0)) for r in _read_buckets()]
    # Clip to last 365 days for a 1y baseline (rolls in as data accrues).
    if len(history) > 365:
        history = history[-365:]
    if not history:
        return 50.0
    below = sum(1 for v in history if v < count)
    return round(100.0 * below / len(history), 1)


# --- Data-quality wiring ---------------------------------------------------

# Mirrors the shape of fleet_service / inventory_service / etc. so
# `data_quality.compute_quality_envelope()` picks "hormuz" up via the
# usual provider scan.

_DQ_LAST_FETCH: dict[str, object] = {
    "last_good_at": None,
    "n_obs": None,
    "latency_ms": None,
    "message": None,
    "status": "amber",  # default until first successful fetch
}
_DQ_STATE_LOCK = threading.Lock()


def get_last_fetch_state() -> dict[str, object]:
    """Snapshot dict — same contract as the other providers."""
    with _DQ_STATE_LOCK:
        return dict(_DQ_LAST_FETCH)


def record_fetch_success(
    *,
    n_obs: Optional[int],
    latency_ms: Optional[int] = None,
    message: Optional[str] = None,
    degraded: bool = False,
) -> None:
    with _DQ_STATE_LOCK:
        _DQ_LAST_FETCH.update(
            {
                "last_good_at": datetime.now(timezone.utc),
                "n_obs": n_obs,
                "latency_ms": latency_ms,
                "message": message,
                "status": "amber" if degraded else "green",
            }
        )


def record_fetch_failure(message: str) -> None:
    with _DQ_STATE_LOCK:
        _DQ_LAST_FETCH.update(
            {"message": message, "status": "red"}
        )


# --- Envelope --------------------------------------------------------------


def compute_envelope() -> dict[str, Any]:
    """Bundle the live data into the shape `/api/geopolitical/hormuz`
    serves. Persists today's bucket on every call so the trend keeps
    accruing as the system runs.
    """
    t0 = _time.monotonic()
    try:
        count = count_24h_transits()
    except Exception as exc:
        record_fetch_failure(
            f"Hormuz fetch failed: {type(exc).__name__}: {exc}"
        )
        raise
    record_daily_count(count)
    pct = percentile_vs_history(count)
    trend = trend_30d()
    latency_ms = int((_time.monotonic() - t0) * 1000.0)
    record_fetch_success(n_obs=count, latency_ms=latency_ms)
    return {
        "count_24h": count,
        "percentile_1y": pct,
        "trend_30d": trend,
    }
