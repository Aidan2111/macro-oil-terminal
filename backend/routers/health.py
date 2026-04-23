"""Health endpoints.

`router` is mounted at `/` so `GET /health` works without a prefix
(App Service warmup probe hits this). `api_router` is mounted under
`/api` so `GET /api/health` is available to the frontend wrapper.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])
api_router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, bool]:
    """Return a minimal ok payload for liveness probes."""
    return {"ok": True}


@api_router.get("/health")
def api_health() -> dict[str, bool]:
    """Same shape as `/health`, served under `/api` for SWA proxy."""
    return {"ok": True}
