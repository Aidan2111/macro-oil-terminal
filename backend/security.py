"""Security helpers — origin allowlist + persistent rate limiter for
/api/positions/execute.

Lives outside `main.py` so it's testable in isolation. Wave 4 hardening,
review #14 findings S-3 (origin allowlist) and S-4 (persistent rate
limit). Read endpoints keep the global wildcard CORS; this module is
only consulted on the write path.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Iterable

from fastapi import HTTPException, Request


# ---------------------------------------------------------------------------
# S-3 — Origin allowlist for /api/positions/execute
# ---------------------------------------------------------------------------

# Production SWA + a localhost dev fallback. The global FastAPI CORSMiddleware
# stays as `allow_origins=["*"]` for the read-only endpoints; this allowlist
# is checked *additionally* on the write path.
EXECUTE_ALLOWED_ORIGINS: tuple[str, ...] = (
    "https://delightful-pebble-00d8eb30f.7.azurestaticapps.net",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
)


def _origin_allowed(origin: str | None, allowlist: Iterable[str]) -> bool:
    """Return True iff `origin` exactly matches one entry in `allowlist`."""
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
        return
    if not _origin_allowed(origin, EXECUTE_ALLOWED_ORIGINS):
        raise HTTPException(
            status_code=403,
            detail=f"Origin '{origin}' is not allowed for /api/positions/execute.",
        )


# ---------------------------------------------------------------------------
# S-4 — Persistent rate limiter for /api/positions/execute
# ---------------------------------------------------------------------------

# Inner gate (per-call floor): one request per 2s.
EXECUTE_MIN_INTERVAL_S: float = 2.0
# Outer gate (burst ceiling): 30 requests per 5-minute window.
EXECUTE_WINDOW_S: float = 300.0
EXECUTE_WINDOW_MAX: int = 30


def _state_path() -> Path:
    """Resolve the rate-limit state file path.

    Uses `RATE_LIMIT_STATE_DIR` env var when set (tests + alt App Service
    home dirs), else `${HOME or /home/site}/data`.
    """
    base = os.environ.get("RATE_LIMIT_STATE_DIR")
    if base:
        return Path(base) / "rate-limit-execute.json"
    home = os.environ.get("HOME", "/home/site")
    return Path(home) / "data" / "rate-limit-execute.json"


_lock = asyncio.Lock()


def _load_state(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        # Corrupt or unreadable — start fresh; don't fail the request.
        return {}
    return {}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f)
    tmp.replace(path)


def _reset_state_for_test() -> None:
    """Test hook — wipe the on-disk bucket so each test starts clean."""
    p = _state_path()
    try:
        if p.exists():
            p.unlink()
    except OSError:
        pass


async def enforce_execute_rate_limit(_: Request) -> None:
    """FastAPI dependency — 429 if the caller exceeds either gate.

    Inner floor: at most one execute every `EXECUTE_MIN_INTERVAL_S` seconds.
    Outer ceiling: at most `EXECUTE_WINDOW_MAX` executes in the trailing
    `EXECUTE_WINDOW_S` seconds.

    State is file-backed (single-process App Service today; survives the
    container restart that the previous in-memory bucket lost). Replace
    with Redis when the App Service scales out.
    """
    now = time.time()
    state_path = _state_path()
    async with _lock:
        state = _load_state(state_path)
        last = float(state.get("last_call", 0.0))
        timestamps: list[float] = [
            float(t) for t in state.get("timestamps", []) if isinstance(t, (int, float))
        ]
        # Drop entries outside the trailing window.
        timestamps = [t for t in timestamps if now - t < EXECUTE_WINDOW_S]

        # Inner gate.
        if last and now - last < EXECUTE_MIN_INTERVAL_S:
            retry = max(1, int(EXECUTE_MIN_INTERVAL_S - (now - last) + 0.5))
            raise HTTPException(
                status_code=429,
                detail=f"Execute rate limit: 1 request per {int(EXECUTE_MIN_INTERVAL_S)}s.",
                headers={"Retry-After": str(retry)},
            )
        # Outer gate.
        if len(timestamps) >= EXECUTE_WINDOW_MAX:
            oldest = min(timestamps)
            retry = max(1, int(EXECUTE_WINDOW_S - (now - oldest) + 0.5))
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Execute burst limit: {EXECUTE_WINDOW_MAX} requests per "
                    f"{int(EXECUTE_WINDOW_S)}s."
                ),
                headers={"Retry-After": str(retry)},
            )

        timestamps.append(now)
        state["last_call"] = now
        state["timestamps"] = timestamps
        try:
            _save_state(state_path, state)
        except OSError:
            # If we cannot persist the bucket, log-and-continue. The next
            # request will rebuild from an empty file — a harmless re-bucket.
            # An observability hook could fan this out to App Insights.
            pass
