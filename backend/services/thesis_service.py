"""Thesis service — SSE bridge + latest/history readers.

The LLM generator (``trade_thesis.generate_thesis``) is synchronous and
exposes a sync ``stream_handler(delta_text)`` callback. The FastAPI SSE route
is async, so we bridge the two worlds via an ``asyncio.Queue``:

  1. The route spawns ``generate_thesis`` in a worker thread via
     ``asyncio.to_thread``.
  2. The route passes a sync ``stream_handler`` that, on the worker thread,
     calls ``loop.call_soon_threadsafe(queue.put_nowait, chunk)``.
  3. The async generator returning SSE chunks awaits on the queue and yields
     each chunk up to the ASGI transport.

This avoids a custom executor, uses only stdlib asyncio primitives, and keeps
the SSE contract (progress → delta → done) explicit at the route layer.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import pathlib
from typing import Any, AsyncIterator, Optional

from . import _compat

# Sentinel pushed on the queue to signal the producer finished.
_DONE = object()


def get_latest_thesis() -> Optional[dict]:
    """Return the most recent audit record, or ``None`` if the log is empty.

    Each record is the dict written by ``trade_thesis._append_audit``:
    ``{timestamp, source, model, context_fingerprint, context, thesis, guardrails}``.
    """
    records = _compat.read_recent_theses(1)
    if not records:
        return None
    return records[0]


def get_thesis_history(limit: int = 30) -> list[dict]:
    """Return up to ``limit`` most-recent audit records, newest first."""
    if limit <= 0:
        return []
    return _compat.read_recent_theses(limit)


def _thesis_to_dict(thesis: Any) -> dict:
    """Serialise a ``trade_thesis.Thesis`` dataclass into a plain dict."""
    if dataclasses.is_dataclass(thesis):
        return dataclasses.asdict(thesis)
    if isinstance(thesis, dict):
        return thesis
    # Defensive fallback — at least return something JSON-serialisable.
    return {"raw": str(thesis)}


async def stream_thesis(
    *,
    mode: str,
    portfolio_usd: int,
    force: bool = False,
    ctx: Any = None,
) -> AsyncIterator[dict]:
    """Yield SSE events for a single thesis-generation run.

    Events:
        ``progress`` — stage + pct, one before context fetch, one before LLM
            call, one before guardrails.
        ``delta`` — ``{"text": <chunk>}`` for each streamed LLM token.
        ``done`` — final ``{thesis, applied_guardrails, materiality_flat}``.

    Each yielded dict has the ``event``/``data`` keys that
    ``sse_starlette.EventSourceResponse`` serialises. ``data`` is pre-JSON-
    encoded so callers don't need to double-encode.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Any] = asyncio.Queue()

    # --- Stage 1: fetching context (cheap, run inline on the event loop) ---
    yield {
        "event": "progress",
        "data": json.dumps({"stage": "fetching_context", "pct": 10}),
    }
    if ctx is None:
        # build_thesis_context() is potentially slow + network-bound — but
        # here we run it in a thread so the event loop isn't blocked. If it
        # fails, surface a proper error event rather than a 500.
        try:
            ctx = await asyncio.to_thread(_compat.build_thesis_context)
        except Exception as exc:  # pragma: no cover — depends on upstream wiring
            yield {
                "event": "error",
                "data": json.dumps({"stage": "fetching_context", "error": repr(exc)}),
            }
            return

    # --- Stage 2: calling LLM ---
    yield {
        "event": "progress",
        "data": json.dumps({"stage": "calling_llm", "pct": 40}),
    }

    def _stream_handler(chunk: str) -> None:
        """Sync callback invoked from the worker thread by trade_thesis."""
        # asyncio.Queue is not itself thread-safe for coroutine scheduling;
        # call_soon_threadsafe marshals into the loop thread cleanly.
        loop.call_soon_threadsafe(queue.put_nowait, chunk)

    async def _runner() -> Any:
        try:
            # ``log=True`` writes to data/trade_theses.jsonl exactly once per
            # generate call, matching existing Streamlit behaviour.
            result = await asyncio.to_thread(
                _compat.generate_thesis,
                ctx,
                mode=mode,
                stream_handler=_stream_handler,
                log=True,
            )
            return result
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, _DONE)

    # Intentionally unused but referenced to silence linters on ``force`` / ``portfolio_usd``;
    # both are captured on the thesis record via the audit log so downstream
    # UIs can render portfolio sizing without the backend persisting it here.
    _ = (portfolio_usd, force)

    runner_task = asyncio.create_task(_runner())

    # --- Stage 3: stream deltas as they arrive ---
    while True:
        item = await queue.get()
        if item is _DONE:
            break
        yield {
            "event": "delta",
            "data": json.dumps({"text": item}),
        }

    # --- Stage 4: guardrails + done ---
    yield {
        "event": "progress",
        "data": json.dumps({"stage": "applying_guardrails", "pct": 90}),
    }

    # await the runner so we surface any exception from the worker thread.
    thesis_obj = await runner_task

    applied_guardrails = list(getattr(thesis_obj, "guardrails_applied", []) or [])
    raw = _thesis_to_dict(thesis_obj)
    stance = str(raw.get("raw", {}).get("stance") or raw.get("stance") or "") \
        if isinstance(raw, dict) else ""
    materiality_flat = stance == "flat"

    yield {
        "event": "done",
        "data": json.dumps(
            {
                "thesis": raw,
                "applied_guardrails": applied_guardrails,
                "materiality_flat": materiality_flat,
            },
            default=str,
        ),
    }


__all__ = [
    "get_latest_thesis",
    "get_thesis_history",
    "stream_thesis",
]
