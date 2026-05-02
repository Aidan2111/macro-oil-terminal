"""Secondary AIS provider — fleetmon.com fallback.

When ``AIS_SECONDARY_API_KEY`` is set, this provider queries fleetmon.com
for live tanker positions. It serves as a redundancy layer for aisstream.io:

- If aisstream.io is silent for >5 min, switch to fleetmon.
- If both are alive, merge and deduplicate by MMSI.

Free tier: fleetmon.com offers a limited API for registered users.
Paid plans start at ~$49/mo for full vessel tracking.

Returns the same DataFrame schema as ``_aisstream.fetch_snapshot()``
so the UI is agnostic to the data source.
"""

from __future__ import annotations

import os
import time
from typing import Optional

import pandas as pd
import requests


_BASE_URL = "https://fleetmon.com/api/v1/vessels"

# AIS message ship types 70-89: Tanker
# We filter for crude oil tankers specifically
_CRUDE_TANKER_TYPES = set(range(80, 90))


def _api_key() -> Optional[str]:
    """Return secondary AIS API key if configured, else None."""
    return os.environ.get("AIS_SECONDARY_API_KEY")


def _fetch_vessels(
    limit: int = 500,
    vessel_type: Optional[str] = None,
    area: Optional[str] = None,
) -> list[dict]:
    """Fetch vessel positions from fleetmon.com API.

    Parameters
    ----------
    limit : int
        Maximum number of vessels to return (default 500).
    vessel_type : str, optional
        Filter by vessel type (e.g., "Tanker", "Cargo").
    area : str, optional
        Filter by geographic area (e.g., "Persian Gulf", "Bosphorus").

    Returns
    -------
    list[dict]
        Vessel position records matching the internal schema.
    """
    key = _api_key()
    if not key:
        raise RuntimeError("AIS_SECONDARY_API_KEY not set")

    params = {
        "api_key": key,
        "limit": min(limit, 1000),  # fleetmon max per request
    }
    if vessel_type:
        params["vessel_type"] = vessel_type
    if area:
        params["area"] = area

    resp = requests.get(_BASE_URL, params=params, timeout=30)
    resp.raise_for_status()

    data = resp.json()
    if not data or "data" not in data:
        raise RuntimeError("fleetmon.com returned empty response")

    vessels = data["data"]
    results = []
    for v in vessels:
        mmsi = v.get("mmsi")
        if not mmsi:
            continue

        ship_type = v.get("type_code")
        # Filter for crude tankers only
        if ship_type and int(ship_type) not in _CRUDE_TANKER_TYPES:
            continue

        lat = v.get("latitude")
        lon = v.get("longitude")
        if lat is None or lon is None:
            continue

        results.append(
            {
                "Vessel_Name": v.get("name") or f"MMSI {mmsi}",
                "MMSI": int(mmsi),
                "Cargo_Volume_bbls": _estimate_volume(v.get("dwt")),
                "Destination": v.get("destination") or "unknown",
                "Flag_State": v.get("flag") or _flag_from_mmsi(int(mmsi)),
                "Latitude": float(lat),
                "Longitude": float(lon),
            }
        )

    return results


def _estimate_volume(dwt: Optional[float]) -> int:
    """Estimate cargo volume in barrels from deadweight tonnage.

    Rule of thumb: 1 DWT ≈ 7 barrels of crude oil.
    """
    if dwt is None:
        return 1_400_000  # heuristic default (VLCC-sized)
    return int(dwt * 7)


def _flag_from_mmsi(mmsi: int) -> str:
    """Rough MID-prefix → flag state mapping (first 3 digits of MMSI).

    Matches the same logic as _aisstream.py for consistency.
    """
    prefix = int(str(mmsi)[:3])
    table = {
        351: "Panama", 352: "Panama", 353: "Panama", 354: "Panama",
        636: "Liberia", 637: "Liberia",
        366: "United States", 367: "United States", 368: "United States", 369: "United States",
        422: "Iran",
        273: "Russia",
        538: "Marshall Islands",
        215: "Malta", 229: "Malta", 248: "Malta", 249: "Malta", 256: "Malta",
        239: "Greece", 240: "Greece", 241: "Greece",
        563: "Singapore", 564: "Singapore", 565: "Singapore", 566: "Singapore", 567: "Singapore",
        775: "Venezuela",
    }
    return table.get(prefix, "Other")


def fetch_snapshot(n_vessels: int = 500, area: Optional[str] = None) -> pd.DataFrame:
    """Fetch tanker positions from fleetmon.com and return a DataFrame.

    Parameters
    ----------
    n_vessels : int
        Maximum number of vessels to fetch (default 500).
    area : str, optional
        Geographic filter (e.g., "Persian Gulf").

    Returns
    -------
    pd.DataFrame
        Same schema as ``_aisstream.fetch_snapshot()``.
    """
    records = _fetch_vessels(limit=n_vessels, vessel_type="Tanker", area=area)
    if not records:
        raise RuntimeError("fleetmon.com returned no crude-tanker positions")
    return pd.DataFrame(records)


def health_check(timeout: float = 10.0) -> dict:
    """Return a health-check dict: ok / latency_ms / note."""
    key = _api_key()
    if not key:
        return {"ok": False, "latency_ms": 0, "note": "no AIS_SECONDARY_API_KEY set"}

    t0 = time.monotonic()
    try:
        resp = requests.get(
            _BASE_URL,
            params={"api_key": key, "limit": 1},
            timeout=timeout,
        )
        ok = resp.status_code == 200 and resp.json().get("data")
        return {
            "ok": bool(ok),
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "note": "" if ok else f"status={resp.status_code}",
        }
    except Exception as exc:
        return {
            "ok": False,
            "latency_ms": int((time.monotonic() - t0) * 1000),
            "note": repr(exc)[:120],
        }


__all__ = ["fetch_snapshot", "health_check"]