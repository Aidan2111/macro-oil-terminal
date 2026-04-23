"""Fleet endpoint — STUB.

Phase 7 wires this to the tanker-tracks data source.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["fleet"])


@router.get("/fleet")
def fleet() -> dict[str, object]:
    """Placeholder response."""
    return {
        "status": "stub",
        "message": "Phase 7 wires /api/fleet to the tanker-tracks feed",
        "tanks": [],
    }
