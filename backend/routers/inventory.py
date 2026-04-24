"""Inventory endpoint.

``GET /api/inventory`` returns current commercial / SPR / Cushing
stocks, 2y of weekly history, and a depletion forecast.

Cached for 15 minutes — EIA data only moves once a week so the TTL is
mostly about rate-limit hygiene.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models.inventory import InventoryResponse
from ..services._cache import TTLCache
from ..services.inventory_service import get_inventory_response

router = APIRouter(tags=["inventory"])

_CACHE: TTLCache[InventoryResponse] = TTLCache(ttl_seconds=15 * 60.0)


def _invalidate_cache() -> None:
    _CACHE.invalidate()


@router.get("/inventory", response_model=InventoryResponse)
def inventory() -> InventoryResponse:
    """Return the cached/freshly-computed inventory snapshot."""
    try:
        return _CACHE.get_or_compute(get_inventory_response)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"inventory upstream error: {exc}",
        ) from exc
