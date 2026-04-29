"""Iranian-flagged + Iran-destined tanker counter (issue #78).

Filters the AISStream feed (already maintained by `fleet_service`) for:

  * `flag_state ∈ {"Iran (Islamic Republic of)", "Iran"}` — defensive
    parsing across the various AIS-ITU spelling variants.
  * `destination ∈ {BANDAR ABBAS, KHARG ISLAND, ASALUYEH, BANDAR-E IMAM}`
    case-insensitive allow-list.

Each matched vessel is bucketed:

  * `iran_export` — destination outside Iran (departing).
  * `iran_import` — destination inside Iran (arriving).

Rolling 7-day counts are computed from the daily-bucket history at
`data/geopolitical/iran_tankers_daily.jsonl`. The endpoint result also
includes the most recent matched vessels for the UI.
"""

from __future__ import annotations

import json
import logging
import pathlib
import threading
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# --- Constants --------------------------------------------------------------

# AIS-ITU variants — defensive parsing for the Iran flag string.
_IRAN_FLAGS = {
    "iran (islamic republic of)",
    "iran islamic republic of",
    "islamic republic of iran",
    "iran",
}

# Iranian crude/condensate ports (case-insensitive contains-match).
_IRANIAN_PORT_TOKENS = (
    "bandar abbas",
    "kharg",          # KHARG ISLAND
    "asaluyeh",       # condensate hub
    "bandar-e imam",
    "bandar imam",
    "bandar mahshahr",
    "siri",           # Siri Island terminal
    "lavan",
)


def _norm(s: object) -> str:
    return str(s or "").strip().lower()


def is_iranian_flagged(flag_state: object) -> bool:
    """Return True if `flag_state` matches one of the AIS Iran variants."""
    return _norm(flag_state) in _IRAN_FLAGS


def is_iran_bound(destination: object) -> bool:
    """Return True if `destination` contains one of the Iranian-port tokens."""
    d = _norm(destination)
    if not d:
        return False
    return any(tok in d for tok in _IRANIAN_PORT_TOKENS)


def classify_vessel(vessel: dict[str, Any]) -> Optional[str]:
    """Classify a vessel as ``iran_export``, ``iran_import``, or None.

    Logic:
      * Flag is Iran AND destination NOT in Iran → ``iran_export``
        (Iranian-flagged tanker leaving).
      * Destination IS in Iran → ``iran_import``
        (any-flag tanker headed to an Iranian port).
      * Both true (Iranian flag, Iranian destination) → ``iran_import``
        (cabotage / domestic — counted as import for our purposes).
      * Neither → None (irrelevant to this tile).
    """
    flag = vessel.get("Flag_State") or vessel.get("flag_state") or vessel.get("flag")
    dest = vessel.get("Destination") or vessel.get("destination")
    iranian_flag = is_iranian_flagged(flag)
    iran_destination = is_iran_bound(dest)
    if iran_destination:
        return "iran_import"
    if iranian_flag:
        return "iran_export"
    return None


# --- Persistence (daily buckets) -------------------------------------------

_BUCKET_PATH = pathlib.Path("data/geopolitical/iran_tankers_daily.jsonl")
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
    exports: int,
    imports: int,
    today: Optional[str] = None,
) -> None:
    """Persist today's export + import counts (higher-water-mark per day)."""
    today = today or _today_iso()
    _BUCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _BUCKET_LOCK:
        rows = _read_buckets()
        replaced = False
        for r in rows:
            if r.get("date") == today:
                r["exports"] = max(int(r.get("exports", 0)), int(exports))
                r["imports"] = max(int(r.get("imports", 0)), int(imports))
                replaced = True
                break
        if not replaced:
            rows.append({"date": today, "exports": int(exports), "imports": int(imports)})
        rows.sort(key=lambda r: r.get("date", ""))
        if len(rows) > 366:
            rows = rows[-366:]
        _BUCKET_PATH.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def rolling_totals(*, days: int = 7) -> dict[str, int]:
    """Return the last `days` days' summed exports + imports."""
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


def latest_matches() -> tuple[int, int, list[dict[str, Any]]]:
    """Walk fleet_service._latest_by_mmsi and return (exports, imports,
    sample_vessels). Sample is at most 25 most-recent matches for UI."""
    from . import fleet_service  # local import to avoid cycles

    cutoff = _time.time() - 24 * 3600
    exp_count = imp_count = 0
    samples: list[dict[str, Any]] = []
    for mmsi, vessel in fleet_service._latest_by_mmsi.items():
        ts = vessel.get("_ingested_at")
        if isinstance(ts, (int, float)) and ts < cutoff:
            continue
        bucket = classify_vessel(vessel)
        if bucket is None:
            continue
        if bucket == "iran_export":
            exp_count += 1
        else:
            imp_count += 1
        samples.append(
            {
                "mmsi": mmsi,
                "name": vessel.get("Vessel_Name") or vessel.get("name"),
                "flag": vessel.get("Flag_State") or vessel.get("flag_state"),
                "destination": vessel.get("Destination") or vessel.get("destination"),
                "bucket": bucket,
                "last_seen": (
                    datetime.fromtimestamp(ts, timezone.utc).isoformat()
                    if isinstance(ts, (int, float))
                    else None
                ),
            }
        )
    samples.sort(key=lambda v: v.get("last_seen") or "", reverse=True)
    return exp_count, imp_count, samples[:25]


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
    """Bundle the live counts + 7-day rolling totals + sample vessels."""
    t0 = _time.monotonic()
    try:
        exp_today, imp_today, samples = latest_matches()
    except Exception as exc:
        record_fetch_failure(
            f"Iran tanker fetch failed: {type(exc).__name__}: {exc}"
        )
        raise
    record_daily_buckets(exports=exp_today, imports=imp_today)
    rolling = rolling_totals(days=7)
    latency_ms = int((_time.monotonic() - t0) * 1000.0)
    record_fetch_success(n_obs=exp_today + imp_today, latency_ms=latency_ms)
    return {
        "exports_today": exp_today,
        "imports_today": imp_today,
        "exports_7d": rolling["exports"],
        "imports_7d": rolling["imports"],
        "latest_vessels": samples,
    }
