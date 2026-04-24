"""`/api/fleet/*` routes.

* `GET /fleet/vessels`   — SSE stream (snapshot + deltas + heartbeats).
* `GET /fleet/snapshot`  — synchronous buffer read.
* `GET /fleet/categories` — flag-policy aggregates.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from ..services import fleet_service


router = APIRouter(tags=["fleet"])


@router.get("/fleet/snapshot")
def fleet_snapshot() -> dict[str, object]:
    """Return the current 1000-vessel ring buffer."""
    vessels = fleet_service.get_snapshot()
    return {"count": len(vessels), "vessels": vessels}


@router.get("/fleet/categories")
def fleet_categories() -> dict[str, object]:
    """Return flag-policy category aggregates."""
    return fleet_service.get_categories()


@router.get("/fleet/vessels")
async def fleet_vessels_stream() -> EventSourceResponse:
    """SSE endpoint: initial snapshot, then deltas as they arrive.

    Heartbeats every `fleet_service.HEARTBEAT_SECONDS` seconds keep
    intermediaries from reaping the connection and let clients detect
    disconnects quickly.
    """
    fleet_service._ensure_producer_running()
    queue = await fleet_service.subscribe()

    async def _event_gen():
        try:
            snapshot = fleet_service.get_snapshot()
            yield {
                "event": "snapshot",
                "data": json.dumps(
                    {"count": len(snapshot), "vessels": snapshot},
                    default=str,
                ),
            }
            while True:
                try:
                    vessel = await asyncio.wait_for(
                        queue.get(),
                        timeout=fleet_service.HEARTBEAT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    # sse-starlette treats a `ping` key as a comment-line heartbeat.
                    yield {"comment": "heartbeat"}
                    continue
                yield {
                    "event": "delta",
                    "data": json.dumps(vessel, default=str),
                }
        finally:
            await fleet_service.unsubscribe(queue)

    return EventSourceResponse(
        _event_gen(),
        ping=int(fleet_service.HEARTBEAT_SECONDS) or 1,
    )
