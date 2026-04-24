"""Thesis endpoints.

Four routes:
    * ``POST /api/thesis/generate`` — SSE stream of progress/delta/done.
    * ``GET  /api/thesis/latest``    — newest row from ``data/trade_theses.jsonl``.
    * ``GET  /api/thesis/history``   — up to N most recent rows.
    * ``POST /api/thesis/regenerate`` — same as generate, forces cache bust.

The SSE stream is bridged from the synchronous ``trade_thesis.generate_thesis``
generator via an ``asyncio.Queue``; see ``services.thesis_service.stream_thesis``.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ..services import thesis_service

router = APIRouter(tags=["thesis"])


class ThesisGenerateRequest(BaseModel):
    """Body of POST /api/thesis/generate and /regenerate."""

    mode: Literal["fast", "deep"] = Field(
        default="fast",
        description="LLM tier — ``fast`` uses gpt-4o-mini, ``deep`` uses o4-mini.",
    )
    portfolio_usd: int = Field(
        ...,
        gt=0,
        description="Total portfolio capital in USD (drives position sizing).",
    )


def _sse_response(body: ThesisGenerateRequest, *, force: bool) -> EventSourceResponse:
    async def _generator():
        async for evt in thesis_service.stream_thesis(
            mode=body.mode,
            portfolio_usd=body.portfolio_usd,
            force=force,
        ):
            yield evt

    # ``media_type="text/event-stream"`` + ``ping=15`` keeps most proxies
    # from buffering/killing the connection during slow LLM calls.
    return EventSourceResponse(_generator(), ping=15)


@router.post("/thesis/generate")
def thesis_generate(body: ThesisGenerateRequest) -> EventSourceResponse:
    """SSE stream: progress → delta(s) → done."""
    return _sse_response(body, force=False)


@router.post("/thesis/regenerate")
def thesis_regenerate(body: ThesisGenerateRequest) -> EventSourceResponse:
    """Same shape as /generate but forces a cache-bust recomputation."""
    return _sse_response(body, force=True)


@router.get("/thesis/latest")
def thesis_latest() -> dict:
    """Return the newest row from ``data/trade_theses.jsonl`` (or empty)."""
    latest = thesis_service.get_latest_thesis()
    if latest is None:
        return {"thesis": None, "empty": True}
    return {"thesis": latest, "empty": False}


@router.get("/thesis/history")
def thesis_history(
    limit: int = Query(30, ge=1, le=500, description="Max rows to return."),
) -> dict:
    """Return up to ``limit`` most-recent thesis rows (newest first)."""
    rows = thesis_service.get_thesis_history(limit)
    return {"count": len(rows), "theses": rows}


__all__ = ["router"]
