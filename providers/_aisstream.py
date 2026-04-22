"""aisstream.io realtime AIS provider (key-gated).

When ``AISSTREAM_API_KEY`` is set, this module opens a short-lived
websocket subscription to aisstream.io and collects a snapshot of
active crude-tanker positions.

The free tier requires a GitHub-linked account but no credit card:
https://aisstream.io/apikeys

Returns the same columns as the historical snapshot so the UI is
agnostic to the data source.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Optional

import pandas as pd


_WS_URL = "wss://stream.aisstream.io/v0/stream"

# Ship types 70-89 in ITU M.1371: 80 = Tanker, 84 = tanker (hazardous category A)
_CRUDE_TANKER_TYPES = set(range(80, 90))


async def _collect_snapshot(api_key: str, seconds: int, n_max: int) -> list[dict]:
    try:
        import websockets  # type: ignore
    except ImportError as exc:
        raise RuntimeError("websockets package required for aisstream.io") from exc

    sub = {
        "APIKey": api_key,
        # Global bounding box excluding poles
        "BoundingBoxes": [[[-85, -180], [85, 180]]],
        "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
    }

    records: dict[int, dict] = {}
    static: dict[int, dict] = {}
    deadline = time.monotonic() + seconds

    async with websockets.connect(_WS_URL, max_size=2**22, ping_interval=20) as ws:
        await ws.send(json.dumps(sub))
        while time.monotonic() < deadline and len(records) < n_max:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=max(1.0, deadline - time.monotonic()))
            except asyncio.TimeoutError:
                break
            try:
                payload = json.loads(msg)
            except Exception:
                continue
            mtype = payload.get("MessageType")
            meta = payload.get("MetaData", {}) or {}
            body = payload.get("Message", {}) or {}
            mmsi = meta.get("MMSI") or body.get("UserID")
            if not mmsi:
                continue
            if mtype == "ShipStaticData":
                inner = body.get("ShipStaticData", {}) or {}
                static[mmsi] = {
                    "name": (inner.get("Name") or meta.get("ShipName") or "").strip(),
                    "type": inner.get("Type"),
                }
            elif mtype == "PositionReport":
                inner = body.get("PositionReport", {}) or {}
                lat = inner.get("Latitude")
                lon = inner.get("Longitude")
                if lat is None or lon is None:
                    continue
                records[mmsi] = {
                    "mmsi": mmsi,
                    "lat": lat,
                    "lon": lon,
                    "cog": inner.get("Cog"),
                    "sog": inner.get("Sog"),
                    "ts": meta.get("time_utc"),
                }

    merged: list[dict] = []
    for mmsi, pos in records.items():
        s = static.get(mmsi, {})
        ship_type = s.get("type")
        if ship_type is not None and ship_type not in _CRUDE_TANKER_TYPES:
            continue
        merged.append(
            {
                "Vessel_Name": s.get("name") or f"MMSI {mmsi}",
                "MMSI": mmsi,
                "Cargo_Volume_bbls": 1_400_000,  # heuristic until loadline/DWT wired
                "Destination": "unknown",
                "Flag_State": _flag_from_mmsi(mmsi),
                "Latitude": pos["lat"],
                "Longitude": pos["lon"],
            }
        )
    return merged


def _flag_from_mmsi(mmsi: int) -> str:
    """Rough MID-prefix → flag state mapping (first 3 digits of MMSI)."""
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


def fetch_snapshot(n_vessels: int = 500, seconds: int = 20) -> pd.DataFrame:
    """Open an aisstream.io websocket subscription for ``seconds`` and return a DataFrame.

    Raises ``RuntimeError`` if ``AISSTREAM_API_KEY`` isn't set or the
    websockets dependency isn't available.
    """
    api_key = os.environ.get("AISSTREAM_API_KEY")
    if not api_key:
        raise RuntimeError("AISSTREAM_API_KEY not set")
    records = asyncio.run(_collect_snapshot(api_key, seconds=seconds, n_max=n_vessels))
    if not records:
        raise RuntimeError("aisstream.io returned no crude-tanker positions in the window")
    return pd.DataFrame(records)
