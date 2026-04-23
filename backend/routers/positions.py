"""Positions endpoint — STUB.

Phase 8 wires this to the Alpaca adapter once P1.2 auth lands.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["positions"])


@router.get("/positions")
def positions() -> dict[str, object]:
    """Placeholder response."""
    return {
        "status": "stub",
        "message": "Phase 8 wires /api/positions to the Alpaca adapter",
        "positions": [],
    }
