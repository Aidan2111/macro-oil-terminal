"""FastAPI application factory.

Creates the app with CORS configured for the Static Web Apps origin
and mounts the router modules. Kept small — every concern lives in a
submodule.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import (
    backtest,
    build_info,
    cftc,
    fleet,
    health,
    inventory,
    positions,
    spread,
    thesis,
)


def _allowed_origins() -> list[str]:
    """Return the list of allowed CORS origins.

    Reads `BACKEND_ALLOWED_ORIGINS` (comma-separated). Defaults permit
    local dev + a wildcard for *.azurestaticapps.net that the real
    proxy will bypass anyway (/api/* is same-origin through SWA).
    """
    raw = os.environ.get("BACKEND_ALLOWED_ORIGINS", "")
    if raw.strip():
        return [o.strip() for o in raw.split(",") if o.strip()]
    return [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://*.azurestaticapps.net",
    ]


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

    # Root health (no /api prefix) — used by App Service warmup probes.
    app.include_router(health.router)

    # All product routes live under /api.
    app.include_router(build_info.router, prefix="/api")
    app.include_router(health.api_router, prefix="/api")
    app.include_router(spread.router, prefix="/api")
    app.include_router(thesis.router, prefix="/api")
    app.include_router(backtest.router, prefix="/api")
    app.include_router(positions.router, prefix="/api")
    app.include_router(cftc.router, prefix="/api")
    app.include_router(inventory.router, prefix="/api")
    app.include_router(fleet.router, prefix="/api")

    return app


app = create_app()
