"""Fleet service — single AISStream consumer -> per-client SSE fan-out.

Structure
---------
Background task (`_producer_task`) holds the sole websocket connection
to aisstream.io. For every `PositionReport` it:

  1. Updates the module-level `_latest_by_mmsi` dict (dedup by MMSI).
  2. Appends to `_ring` (a deque bounded by `BUFFER_MAX = 1000`).
  3. Fans the vessel-dict out to every subscriber's `asyncio.Queue`.

SSE endpoints call `subscribe()` to get a fresh queue, then
`unsubscribe()` on disconnect. Tests can push events directly via
`publish_delta()` and skip the real websocket via the
`_ensure_producer_running` hook.

The root `providers/_aisstream.py` module is NOT modified — we reuse its
flag-state helper only.
"""

from __future__ import annotations

import asyncio
import collections
import contextlib
import json
import os
import time
from typing import Any, Callable, Iterable

from . import _compat  # noqa: F401 (path-munging side effect)


# --- Constants ---------------------------------------------------------------

BUFFER_MAX = 1000
HEARTBEAT_SECONDS = 15.0
QUEUE_MAX = 256  # per-client backpressure cap

# Policy buckets used by /api/fleet/categories.
_JONES_ACT_FLAGS = {"United States"}
_DOMESTIC_FLAGS = {"United States", "Canada", "Mexico"}
_SHADOW_FLAGS = {
    "Liberia",
    "Marshall Islands",
    "Panama",
    "Cook Islands",
    "Comoros",
    "Gabon",
    "San Marino",
    "Saint Kitts and Nevis",
}
_SANCTIONED_FLAGS = {"Iran", "Venezuela", "Russia", "North Korea", "Syria"}


# --- Module-level state ------------------------------------------------------

_latest_by_mmsi: "dict[int, dict[str, Any]]" = {}
_ring: "collections.deque[int]" = collections.deque(maxlen=BUFFER_MAX)
_subscribers: "set[asyncio.Queue]" = set()
_producer_task: "asyncio.Task | None" = None
_producer_started_at: float = 0.0


# --- Public API --------------------------------------------------------------


def reset_state() -> None:
    """Wipe buffer + subscribers. Test hook."""
    global _producer_task
    _latest_by_mmsi.clear()
    _ring.clear()
    _subscribers.clear()
    if _producer_task is not None and not _producer_task.done():
        _producer_task.cancel()
    _producer_task = None


def get_snapshot() -> list[dict[str, Any]]:
    """Return the current vessel buffer (up to BUFFER_MAX entries)."""
    return [_latest_by_mmsi[m] for m in list(_ring) if m in _latest_by_mmsi]


def get_categories() -> dict[str, Any]:
    """Aggregate counts per policy category."""
    vessels = get_snapshot()
    buckets: dict[str, dict[str, Any]] = {
        "jones_act": {"count": 0, "vessels": []},
        "domestic": {"count": 0, "vessels": []},
        "shadow": {"count": 0, "vessels": []},
        "sanctioned": {"count": 0, "vessels": []},
    }
    for v in vessels:
        flag = (v.get("Flag_State") or "").strip()
        if flag in _JONES_ACT_FLAGS:
            buckets["jones_act"]["count"] += 1
            buckets["jones_act"]["vessels"].append(v.get("MMSI"))
        if flag in _DOMESTIC_FLAGS:
            buckets["domestic"]["count"] += 1
            buckets["domestic"]["vessels"].append(v.get("MMSI"))
        if flag in _SHADOW_FLAGS:
            buckets["shadow"]["count"] += 1
            buckets["shadow"]["vessels"].append(v.get("MMSI"))
        if flag in _SANCTIONED_FLAGS:
            buckets["sanctioned"]["count"] += 1
            buckets["sanctioned"]["vessels"].append(v.get("MMSI"))
    return {"categories": buckets, "total": len(vessels)}


async def subscribe() -> "asyncio.Queue":
    """Register a new subscriber queue. Caller must `unsubscribe` on exit."""
    q: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX)
    _subscribers.add(q)
    return q


async def unsubscribe(q: "asyncio.Queue") -> None:
    """Remove a subscriber."""
    _subscribers.discard(q)


async def publish_delta(vessel: dict[str, Any]) -> None:
    """Ingest a vessel update + broadcast to every subscriber queue.

    Test hook + the real producer's single entry point, so there's
    exactly ONE write path into the buffer and the fan-out.
    """
    _ingest(vessel)
    dead: list[asyncio.Queue] = []
    for q in list(_subscribers):
        try:
            q.put_nowait(vessel)
        except asyncio.QueueFull:
            # Drop the slowest clients rather than backpressure the WS.
            dead.append(q)
    for q in dead:
        _subscribers.discard(q)


# --- Internal ---------------------------------------------------------------


def _ingest(vessel: dict[str, Any]) -> None:
    mmsi = vessel.get("MMSI")
    if mmsi is None:
        return
    if mmsi in _latest_by_mmsi:
        # Move-to-most-recent: rewrite the deque entry.
        try:
            _ring.remove(mmsi)
        except ValueError:
            pass
    _ring.append(mmsi)
    _latest_by_mmsi[mmsi] = vessel
    # Keep the dict bounded alongside the deque: evict MMSIs that fell off.
    if len(_latest_by_mmsi) > BUFFER_MAX:
        live = set(_ring)
        for m in list(_latest_by_mmsi):
            if m not in live:
                del _latest_by_mmsi[m]


def _ensure_producer_running() -> None:
    """Start the background AISStream consumer if not already running.

    Tests monkey-patch this to a no-op so they don't open a real socket.
    """
    global _producer_task, _producer_started_at
    if _producer_task is not None and not _producer_task.done():
        return
    # Only start if we're inside a running loop (the SSE handler is).
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    _producer_started_at = time.monotonic()
    _producer_task = loop.create_task(_run_producer(), name="fleet-aisstream-consumer")


async def _run_producer() -> None:
    """Single consumer loop: open the WS and forward positions to subscribers.

    Swallows all errors and retries with backoff — the rest of the system
    should never care that AISStream flapped.
    """
    api_key = os.environ.get("AISSTREAM_API_KEY")
    if not api_key:
        return  # No key -> snapshot stays whatever callers seeded.

    try:
        import websockets  # type: ignore
    except ImportError:
        return

    backoff = 1.0
    sub = {
        "APIKey": api_key,
        "BoundingBoxes": [[[-85, -180], [85, 180]]],
        "FilterMessageTypes": ["PositionReport", "ShipStaticData"],
    }
    static: dict[int, dict[str, Any]] = {}

    while True:
        try:
            async with websockets.connect(
                "wss://stream.aisstream.io/v0/stream",
                max_size=2**22,
                ping_interval=20,
            ) as ws:
                await ws.send(json.dumps(sub))
                backoff = 1.0
                async for raw in ws:
                    try:
                        payload = json.loads(raw)
                    except Exception:
                        continue
                    vessel = _shape_from_aisstream(payload, static)
                    if vessel is not None:
                        await publish_delta(vessel)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Never leak exceptions to the loop; back off and retry.
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)


def _shape_from_aisstream(
    payload: dict[str, Any], static: dict[int, dict[str, Any]]
) -> dict[str, Any] | None:
    """Project an AISStream message into our vessel dict shape."""
    mtype = payload.get("MessageType")
    meta = payload.get("MetaData") or {}
    body = payload.get("Message") or {}
    mmsi = meta.get("MMSI") or body.get("UserID")
    if not mmsi:
        return None
    if mtype == "ShipStaticData":
        inner = body.get("ShipStaticData") or {}
        static[mmsi] = {
            "name": (inner.get("Name") or meta.get("ShipName") or "").strip(),
            "type": inner.get("Type"),
        }
        return None
    if mtype != "PositionReport":
        return None
    inner = body.get("PositionReport") or {}
    lat = inner.get("Latitude")
    lon = inner.get("Longitude")
    if lat is None or lon is None:
        return None
    s = static.get(mmsi, {})
    return {
        "Vessel_Name": s.get("name") or f"MMSI {mmsi}",
        "MMSI": mmsi,
        "Cargo_Volume_bbls": 1_400_000,
        "Destination": "unknown",
        "Flag_State": _flag_from_mmsi(mmsi),
        "Latitude": lat,
        "Longitude": lon,
    }


def _flag_from_mmsi(mmsi: int) -> str:
    """MID-prefix -> flag state. Mirrors providers/_aisstream.py (wrapped)."""
    try:
        prefix = int(str(mmsi)[:3])
    except Exception:
        return "Other"
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
# Q1-DATA-QUALITY-WIRING — wrapper that calls record_fetch_success/failure
# on each vessel ingestion via publish_delta.
# ---------------------------------------------------------------------------

import logging as _dq_logging

_dq_log = _dq_logging.getLogger(__name__)

_real_publish_delta = publish_delta


async def publish_delta(vessel: dict[str, Any]) -> None:  # type: ignore[no-redef]
    t0 = time.monotonic()
    try:
        await _real_publish_delta(vessel)
    except Exception as exc:
        record_fetch_failure(f"AISStream ingest failed: {type(exc).__name__}: {exc}")
        raise
    latency_ms = int((time.monotonic() - t0) * 1000.0)
    n_obs = len(_latest_by_mmsi)
    degraded = False
    msg = None
    try:
        from backend.services.data_quality import GuardViolation, guard_aisstream_vessels
        vessels = [
            {"mmsi": v.get("MMSI"), "lat": v.get("Latitude"), "lon": v.get("Longitude")}
            for v in [vessel]
        ]
        try:
            guard_aisstream_vessels(vessels)
        except GuardViolation as gv:
            degraded = True
            msg = str(gv)
            _dq_log.warning("AISStream guard tripped: %s", gv)
    except Exception:
        pass
    record_fetch_success(n_obs=n_obs, latency_ms=latency_ms,
                         message=msg, degraded=degraded)
