"""Security helpers — origin allowlist for /api/positions/execute.

Lives outside `main.py` so it's testable in isolation. Wave 4 hardening,
review #14 finding S-3. Read endpoints keep the global wildcard CORS;
this module is only consulted on the write path.

Note: rate-limit logic for the same route is added in a follow-up commit
(review #14, S-4). Both pieces co-locate here once that lands.
"""

from __future__ import annotations

from typing import Iterable

from fastapi import HTTPException, Request


# Production SWA + a localhost dev fallback. The global FastAPI CORSMiddleware
# stays as `allow_origins=["*"]` for the read-only endpoints; this allowlist
# is checked *additionally* on the write path.
EXECUTE_ALLOWED_ORIGINS: tuple[str, ...] = (
    "https://delightful-pebble-00d8eb30f.7.azurestaticapps.net",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)


def _origin_allowed(origin: str | None, allowlist: Iterable[str]) -> bool:
    """Return True iff `origin` exactly matches one entry in `allowlist`.

    No wildcard, no scheme-folding, no trailing-slash forgiveness.
    Browser-emitted Origin headers are predictable enough that exact match
    is the right primitive here.
    """
    if not origin:
        return False
    return origin in tuple(allowlist)


async def require_execute_origin(request: Request) -> None:
    """FastAPI dependency — 403 the request if Origin is not on the allowlist.

    Empty/absent Origin (server-to-server, curl, Postman, same-origin GETs)
    is allowed: this is a defence-in-depth layer against drive-by browser
    POSTs from a malicious site, not an authn/z primitive. Real auth lands
    in phase-2.
    """
    origin = request.headers.get("origin")
    if origin is None:
        # No Origin header → not a cross-origin browser request.
        return
    if not _origin_allowed(origin, EXECUTE_ALLOWED_ORIGINS):
        raise HTTPException(
            status_code=403,
            detail=f"Origin '{origin}' is not allowed for /api/positions/execute.",
        )
