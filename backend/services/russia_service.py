"""Russia mirror — chokepoint transits + Russian-flagged tankers + OFAC
delta surfaced under a single envelope (issue #82).

This is the structural twin of the Iran service set:

  * `iran_tanker_service` → flag + Iranian-port allow-list
  * `geopolitical_service` (Hormuz) → AISStream geofence

For Russia we cover three export chokepoints:

  * Bosphorus (41.0°N, 29.0°E, 30nm)        — Black Sea exit
  * Novorossiysk (44.7°N, 37.8°E, 30nm)     — Black Sea export port
  * Tuapse (44.1°N, 39.1°E, 30nm)           — Black Sea export port
  * Primorsk (60.4°N, 28.6°E, 30nm)         — Baltic export port

A vessel within ANY fence in the last 24h counts as a "chokepoint
transit" for the day. Russian-flagged tankers are bucketed
exports/imports identically to the Iran service.

Russia-tagged sanctions delta is sourced from the OFAC service
(issue #81); we just surface the russia bucket under our envelope so
the macro-page tile can render it next to the AIS counts without
hitting two endpoints.
"""

from __future__ import annotations

import json
import logging
import math
import pathlib
import threading
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

# --- Constants --------------------------------------------------------------

# Earth radius in nautical miles.
_EARTH_RADIUS_NM = 6371000.0 / 1852.0

# (label, lat, lon, radius_nm).
RUSSIA_FENCES: list[tuple[str, float, float, float]] = [
    ("Bosphorus", 41.0, 29.0, 30.0),
    ("Novorossiysk", 44.7, 37.8, 30.0),
    ("Tuapse", 44.1, 39.1, 30.0),
    ("Primorsk", 60.4, 28.6, 30.0),
]

# Russia flag-state spelling variants from AIS-ITU.
_RUSSIAN_FLAGS = {
    "russia",
    "russian federation",
    "russia (russian federation)",
    "russian federation (russia)",
}


def _norm(s: object) -> str:
    return str(s or "").strip().lower()


def is_russian_flagged(flag_state: object) -> bool:
    return _norm(flag_state) in _RUSSIAN_FLAGS


def _haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return _EARTH_RADIUS_NM * c


def in_any_russia_fence(lat: object, lon: object) -> Optional[str]:
    """Return the fence label the vessel falls inside, or None.

    Defensive about garbage AIS positions: rejects (0,0), NaN, inf,
    non-numeric strings.
    """
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lat_f) and math.isfinite(lon_f)):
        return None
    if lat_f == 0.0 and lon_f == 0.0:
        return None
    for label, c_lat, c_lon, radius in RUSSIA_FENCES:
        if _haversine_nm(c_lat, c_lon, lat_f, lon_f) <= radius:
            return label
    return None


# --- Daily-bucket persistence ----------------------------------------------

_BUCKET_PATH = pathlib.Path("data/geopolitical/russia_daily.jsonl")
_BUCKET_LOCK = threading.Lock()


def _today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _read_buckets() -> list[dict[str, Any]]:
    if not _BUCKET_PATH.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in _BUCKET_PATH.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except Exception:
        return []
    return rows


def record_daily_buckets(
    *,
    chokepoint_transits: int,
    exports: int,
    imports: int,
    today: Optional[str] = None,
) -> None:
    today = today or _today_iso()
    _BUCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _BUCKET_LOCK:
        rows = _read_buckets()
        replaced = False
        for r in rows:
            if r.get("date") == today:
                r["chokepoint_transits"] = max(
                    int(r.get("chokepoint_transits", 0)), int(chokepoint_transits)
                )
                r["exports"] = max(int(r.get("exports", 0)), int(exports))
                r["imports"] = max(int(r.get("imports", 0)), int(imports))
                replaced = True
                break
        if not replaced:
            rows.append(
                {
                    "date": today,
                    "chokepoint_transits": int(chokepoint_transits),
                    "exports": int(exports),
                    "imports": int(imports),
                }
            )
        rows.sort(key=lambda r: r.get("date", ""))
        if len(rows) > 366:
            rows = rows[-366:]
        _BUCKET_PATH.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def percentile_vs_history(value: int, *, key: str = "chokepoint_transits") -> float:
    history = [int(r.get(key, 0)) for r in _read_buckets()]
    if len(history) > 365:
        history = history[-365:]
    if not history:
        return 50.0
    below = sum(1 for v in history if v < value)
    return round(100.0 * below / len(history), 1)


def rolling_totals(*, days: int = 7) -> dict[str, int]:
    rows = _read_buckets()
    today = datetime.now(timezone.utc).date()
    cutoff = today - timedelta(days=days - 1)
    exp = imp = 0
    for r in rows:
        d = r.get("date")
        if not d:
            continue
        try:
            d_obj = datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            continue
        if d_obj < cutoff:
            continue
        exp += int(r.get("exports", 0))
        imp += int(r.get("imports", 0))
    return {"exports": exp, "imports": imp}


# --- Live counts ------------------------------------------------------------


def latest_matches() -> dict[str, Any]:
    """Walk fleet_service._latest_by_mmsi, classify each vessel as
    russia_chokepoint / russia_export / russia_import. Returns counts +
    sample vessels."""
    from . import fleet_service

    cutoff = _time.time() - 24 * 3600
    chokepoint_count = 0
    exp_count = imp_count = 0
    samples: list[dict[str, Any]] = []
    for mmsi, vessel in fleet_service._latest_by_mmsi.items():
        ts = vessel.get("_ingested_at")
        if isinstance(ts, (int, float)) and ts < cutoff:
            continue
        flag = vessel.get("Flag_State") or vessel.get("flag_state") or vessel.get("flag")
        dest = vessel.get("Destination") or vessel.get("destination") or ""
        lat = vessel.get("Latitude")
        lon = vessel.get("Longitude")
        fence = in_any_russia_fence(lat, lon)

        in_chokepoint = fence is not None
        russian_flag = is_russian_flagged(flag)
        # Exports = Russian-flagged + non-Russian destination keyword
        # (any departure from Russian waters), imports = vessel inside
        # a Russian-export-port fence with non-Russian flag (anyone
        # picking up Russian crude).
        is_export = russian_flag and not in_chokepoint  # Russian-flagged at sea
        is_import = (not russian_flag) and in_chokepoint  # foreign in fence

        if in_chokepoint:
            chokepoint_count += 1
        if is_export:
            exp_count += 1
        elif is_import:
            imp_count += 1
        if in_chokepoint or russian_flag:
            samples.append(
                {
                    "mmsi": mmsi,
                    "name": vessel.get("Vessel_Name") or vessel.get("name"),
                    "flag": flag,
                    "destination": dest,
                    "fence": fence,
                    "russian_flag": russian_flag,
                    "last_seen": (
                        datetime.fromtimestamp(ts, timezone.utc).isoformat()
                        if isinstance(ts, (int, float))
                        else None
                    ),
                }
            )

    samples.sort(key=lambda v: v.get("last_seen") or "", reverse=True)
    return {
        "chokepoint_transits": chokepoint_count,
        "exports": exp_count,
        "imports": imp_count,
        "samples": samples[:25],
    }


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


def record_fetch_success(*, n_obs: Optional[int], latency_ms: Optional[int] = None) -> None:
    with _DQ_STATE_LOCK:
        _DQ_LAST_FETCH.update(
            {
                "last_good_at": datetime.now(timezone.utc),
                "n_obs": n_obs,
                "latency_ms": latency_ms,
                "message": None,
                "status": "green",
            }
        )


def record_fetch_failure(message: str) -> None:
    with _DQ_STATE_LOCK:
        _DQ_LAST_FETCH.update({"message": message, "status": "red"})


# --- Envelope --------------------------------------------------------------


def compute_envelope() -> dict[str, Any]:
    t0 = _time.monotonic()
    try:
        live = latest_matches()
    except Exception as exc:
        record_fetch_failure(f"Russia fetch failed: {type(exc).__name__}: {exc}")
        raise

    record_daily_buckets(
        chokepoint_transits=live["chokepoint_transits"],
        exports=live["exports"],
        imports=live["imports"],
    )
    rolling = rolling_totals(days=7)
    pct_1y = percentile_vs_history(live["chokepoint_transits"])

    # Pull Russia-bucket sanctions delta from the OFAC service. Best-
    # effort — failures degrade to None rather than break the envelope.
    sanctions_delta_30d: Optional[int] = None
    try:
        from . import ofac_service  # type: ignore
        ofac_env = ofac_service.compute_envelope()
        delta = ofac_env.get("delta_vs_baseline", {}) or {}
        sanctions_delta_30d = int(delta.get("russia", 0))
    except Exception:
        sanctions_delta_30d = None

    latency_ms = int((_time.monotonic() - t0) * 1000.0)
    record_fetch_success(
        n_obs=live["chokepoint_transits"] + live["exports"] + live["imports"],
        latency_ms=latency_ms,
    )
    return {
        "chokepoint_transits_24h": live["chokepoint_transits"],
        "percentile_1y": pct_1y,
        "exports_today": live["exports"],
        "imports_today": live["imports"],
        "exports_7d": rolling["exports"],
        "imports_7d": rolling["imports"],
        "sanctions_delta_30d": sanctions_delta_30d,
        "latest_vessels": live["samples"],
    }
