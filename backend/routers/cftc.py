"""CFTC commitments endpoint — STUB.

Phase 6 wires this to the existing CFTC provider.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["cftc"])


@router.get("/cftc")
def cftc() -> dict[str, object]:
    """Placeholder response."""
    return {
        "status": "stub",
        "message": "Phase 6 wires /api/cftc to providers.cftc",
        "series": [],
    }
