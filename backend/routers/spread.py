"""Spread endpoint — STUB.

Phase 2 wires this to `cointegration.compute_spread_series`. For now,
returns a hello payload so the frontend scaffold can fetch and render
an `EmptyState`.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["spread"])


@router.get("/spread")
def spread() -> dict[str, object]:
    """Placeholder response. Phase 2 replaces this with real data."""
    return {
        "status": "stub",
        "message": "Phase 2 wires /api/spread to cointegration.compute_spread_series",
        "series": [],
    }
