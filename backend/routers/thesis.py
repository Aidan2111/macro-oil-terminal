"""Thesis endpoints — STUB.

`GET /api/thesis/latest` returns a placeholder. `POST /api/thesis/generate`
returns an SSE stream with a couple of echo events so the frontend can
test its EventSource plumbing.

Phase 4 replaces both with real implementations.
"""

from __future__ import annotations

import asyncio
import json
from typing import AsyncIterator

from fastapi import APIRouter

try:
    from sse_starlette.sse import EventSourceResponse
except ImportError:  # pragma: no cover — dep enforced by requirements.txt
    EventSourceResponse = None  # type: ignore[assignment]

router = APIRouter(tags=["thesis"])


@router.get("/thesis/latest")
def thesis_latest() -> dict[str, object]:
    """Placeholder thesis payload.

    Phase 4 reads the real thesis from the trade-thesis blob store.
    """
    return {
        "status": "stub",
        "message": "Phase 4 wires /api/thesis/latest to the trade-thesis store",
        "thesis": None,
    }


async def _echo_events() -> AsyncIterator[dict[str, str]]:
    yield {"event": "token", "data": "scaffold"}
    await asyncio.sleep(0.01)
    yield {"event": "token", "data": " stub"}
    await asyncio.sleep(0.01)
    yield {
        "event": "done",
        "data": json.dumps({"status": "stub", "text": "scaffold stub"}),
    }


@router.post("/thesis/generate")
async def thesis_generate():
    """SSE stub — emits two token events + a done event."""
    if EventSourceResponse is None:
        return {"status": "sse-starlette not installed"}
    return EventSourceResponse(_echo_events())
