"""Boot-time config checks for auth (P1.1.6).

Surface the minimum env-var contract the rest of the ``auth`` package
needs so ``app.py`` can fail loudly in prod and softly in dev.

Contract:
    * ``is_configured()`` -> bool — True iff all required env vars are
      set and at least one of the two storage-account slots is set.
    * ``boot_check()`` -> None — raises ``AuthNotConfigured`` in prod
      when misconfigured; otherwise logs a single warning and returns.

Kept deliberately dependency-free (stdlib only) so it can be imported
at process start before Streamlit / Azure SDK wake up.
"""
from __future__ import annotations

import logging
import os

_REQUIRED_ENV_VARS: tuple[str, ...] = (
    "GOOGLE_OAUTH_CLIENT_ID",
    "GOOGLE_OAUTH_CLIENT_SECRET",
    "STREAMLIT_COOKIE_SECRET",
)
# Either of these signals a reachable Table Storage backend. Connection
# string wins when both are set; ``STORAGE_ACCOUNT_NAME`` alone means
# we'll fall back to managed identity in prod.
_EITHER_OF: tuple[str, ...] = (
    "STORAGE_ACCOUNT_CONNECTION_STRING",
    "STORAGE_ACCOUNT_NAME",
)

_LOG = logging.getLogger(__name__)
_WARNED = False


class AuthNotConfigured(RuntimeError):
    """Raised by :func:`boot_check` when running in prod without the
    required env vars present."""


def _missing() -> list[str]:
    missing = [v for v in _REQUIRED_ENV_VARS if not os.environ.get(v)]
    if not any(os.environ.get(v) for v in _EITHER_OF):
        missing.append(f"one of {'/'.join(_EITHER_OF)}")
    return missing


def is_configured() -> bool:
    """Return True iff every required auth env var is non-empty."""
    return not _missing()


def boot_check() -> None:
    """Validate auth env at process start.

    * Fully configured -> no-op.
    * Prod + misconfigured -> raise :class:`AuthNotConfigured`.
    * Dev + misconfigured -> log one WARNING and return.
    """
    global _WARNED
    if is_configured():
        return
    if os.environ.get("STREAMLIT_ENV") == "prod":
        raise AuthNotConfigured(f"Missing: {', '.join(_missing())}")
    if not _WARNED:
        _LOG.warning(
            "auth_not_configured — public-only mode (missing: %s)", _missing()
        )
        _WARNED = True
