"""CFTC COT endpoint.

``GET /api/cftc`` returns latest Managed-Money + Commercial net
positions, ``mm_zscore_3y``, and the weekly history covering ~3y.

Cached for 1h — CFTC publishes once a week on Fridays at 15:30 ET.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models.cftc import CFTCResponse
from ..services._cache import TTLCache
from ..services.cftc_service import get_cftc_response

router = APIRouter(tags=["cftc"])

_CACHE: TTLCache[CFTCResponse] = TTLCache(ttl_seconds=60 * 60.0)


def _invalidate_cache() -> None:
    _CACHE.invalidate()


@router.get("/cftc", response_model=CFTCResponse)
def cftc() -> CFTCResponse:
    """Return the cached/freshly-computed COT snapshot."""
    try:
        return _CACHE.get_or_compute(get_cftc_response)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"cftc upstream error: {exc}",
        ) from exc
