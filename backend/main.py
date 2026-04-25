"""FastAPI application factory.

Creates the app with CORS configured for the Static Web Apps origin
and mounts the router modules. Kept small — every concern lives in a
submodule.

Lazy-mount strategy: only `health` and `build_info` are imported at
module load. Every other router is imported and mounted on first
request via a small middleware. This keeps Azure App Service's
container warmup probe (~230s) green even though the deeper routers
pull in sklearn, statsmodels, arch, yfinance, etc. — those imports
cost ~30-40s each on a cold B2 SKU.
"""

from __future__ import annotations

import os
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# Cheap, always-imported routers — used by warmup probe.
from .routers import build_info, health


def _allowed_origins() -> list[str]:
    """Return the list of allowed CORS origins."""
    raw = os.environ.get("BACKEND_ALLOWED_ORIGINS", "")
    if raw.strip():
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://*.azurestaticapps.net",
    ]


# Module-level guard so heavy mounting happens exactly once.
_HEAVY_MOUNTED = False
_HEAVY_LOCK = threading.Lock()


def _mount_heavy_routers(app: FastAPI) -> None:
    """Lazily import + mount the routers that pull in sklearn / pandas /
    yfinance. Called on first matching request, not at module load.

    Idempotent: subsequent calls no-op via the module-level flag.
    """
    global _HEAVY_MOUNTED
    with _HEAVY_LOCK:
        if _HEAVY_MOUNTED:
            return
        # Import here so warmup doesn't pay the full import cost.
        from .routers import (
            backtest,
            cftc,
            fleet,
            inventory,
            positions,
            spread,
            thesis,
        )

        app.include_router(spread.router, prefix="/api")
        app.include_router(thesis.router, prefix="/api")
        app.include_router(backtest.router, prefix="/api")
        app.include_router(positions.router, prefix="/api")
        app.include_router(cftc.router, prefix="/api")
        app.include_router(inventory.router, prefix="/api")
        app.include_router(fleet.router, prefix="/api")
        _HEAVY_MOUNTED = True


class LazyMountMiddleware(BaseHTTPMiddleware):
    """Trigger heavy-router mount on first request that needs it.

    Health and build-info routes don't need the heavy imports; everything
    else does. We check the path prefix and lazy-mount before the
    request reaches the routing layer.
    """

    def __init__(self, app: FastAPI):
        super().__init__(app)
        self._app = app

    async def dispatch(self, request, call_next):
        path = request.url.path
        # Health + build-info: cheap, no heavy mount needed.
        if path in ("/health", "/api/health", "/api/build-info"):
            return await call_next(request)
        # Anything else: ensure heavy routers are mounted.
        if not _HEAVY_MOUNTED:
            try:
                _mount_heavy_routers(self._app)
            except Exception as exc:  # pragma: no cover
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": "backend_warming_up",
                        "detail": str(exc),
                    },
                )
        return await call_next(request)


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    app = FastAPI(
        title="Macro Oil Terminal API",
        version="0.1.0",
        description=(
            "Backend for the Next.js frontend. Parallel-deployed "
            "alongside the Streamlit app during the migration "
            "window."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.add_middleware(LazyMountMiddleware)

    # Always-mounted routers (cheap imports).
    app.include_router(health.router)
    app.include_router(build_info.router, prefix="/api")
    app.include_router(health.api_router, prefix="/api")

    return app


app = create_app()
