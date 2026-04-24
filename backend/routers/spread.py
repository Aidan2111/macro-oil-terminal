"""Spread endpoint.

``GET /api/spread`` returns the latest Brent-WTI prices + spread +
rolling 90d Z-score (``stretch``) + qualitative band + last 90 bars
of history.

Cached for 60s so rapid frontend polls don't hammer yfinance.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models.spread import SpreadResponse
from ..services._cache import TTLCache
from ..services.spread_service import get_spread_response

router = APIRouter(tags=["spread"])

_CACHE: TTLCache[SpreadResponse] = TTLCache(ttl_seconds=60.0)


def _invalidate_cache() -> None:
    """Test hook — reset the TTL cache so ordering-sensitive tests work."""
    _CACHE.invalidate()


@router.get("/spread", response_model=SpreadResponse)
def spread() -> SpreadResponse:
    """Return the cached/freshly-computed spread snapshot."""
    try:
        return _CACHE.get_or_compute(get_spread_response)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"spread upstream error: {exc}",
        ) from exc
