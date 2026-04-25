"""FastAPI application factory.

Lazy-mount strategy: only `health` and `build_info` are imported at
module load. Heavy routers (spread / thesis / fleet / positions / etc.)
are imported and mounted on first request via a small middleware. This
keeps Azure App Service's container warmup probe (~230s) green even
though the deeper routers pull in sklearn, statsmodels, arch, yfinance.
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


# Module-level guards so heavy mounting happens exactly once.
_HEAVY_MOUNTED = False
_HEAVY_LOCK = threading.Lock()


def _mount_heavy_routers(fastapi_app: FastAPI) -> None:
    """Lazily import + mount routers that pull in sklearn / pandas /
    yfinance. Idempotent — second call is a no-op.

    Takes the bare ``FastAPI`` instance (not a middleware-wrapped ASGI
    app) so ``include_router`` resolves correctly.
    """
    global _HEAVY_MOUNTED
    with _HEAVY_LOCK:
        if _HEAVY_MOUNTED:
            return
        from .routers import (
            backtest,
            cftc,
            fleet,
            inventory,
            positions,
            spread,
            thesis,
        )

        fastapi_app.include_router(spread.router, prefix="/api")
        fastapi_app.include_router(thesis.router, prefix="/api")
        fastapi_app.include_router(backtest.router, prefix="/api")
        fastapi_app.include_router(positions.router, prefix="/api")
        fastapi_app.include_router(cftc.router, prefix="/api")
        fastapi_app.include_router(inventory.router, prefix="/api")
        fastapi_app.include_router(fleet.router, prefix="/api")
        _HEAVY_MOUNTED = True


def _make_lazy_middleware(fastapi_app: FastAPI):
    """Closure-bind the FastAPI instance into the middleware so
    ``include_router`` resolves to the bare app, not the
    middleware-wrapped ASGI surface that ``BaseHTTPMiddleware`` exposes
    as ``self.app``.
    """

    class LazyMountMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            path = request.url.path
            # Cheap paths skip the mount.
            if path in ("/health", "/api/health", "/api/build-info"):
                return await call_next(request)
            if not _HEAVY_MOUNTED:
                try:
                    _mount_heavy_routers(fastapi_app)
                except Exception as exc:  # pragma: no cover
                    return JSONResponse(
                        status_code=503,
                        content={
                            "error": "backend_warming_up",
                            "detail": str(exc),
                        },
                    )
            return await call_next(request)

    return LazyMountMiddleware


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""
    app = FastAPI(
        title="Macro Oil Terminal API",
        version="0.1.0",
        description=(
            "Backend for the Next.js frontend. Parallel-deployed "
            "alongside the Streamlit app during the migration window."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.add_middleware(_make_lazy_middleware(app))

    # Always-mounted routers (cheap imports).
    app.include_router(health.router)
    app.include_router(build_info.router, prefix="/api")
    app.include_router(health.api_router, prefix="/api")

    return app


app = create_app()
