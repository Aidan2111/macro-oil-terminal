"""Inventory endpoint — STUB.

Phase 6 wires this to the EIA inventory provider.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["inventory"])


@router.get("/inventory")
def inventory() -> dict[str, object]:
    """Placeholder response."""
    return {
        "status": "stub",
        "message": "Phase 6 wires /api/inventory to providers.eia",
        "series": [],
    }
