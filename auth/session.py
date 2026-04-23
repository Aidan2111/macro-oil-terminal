"""Runtime auth seam — ``current_user()`` + MOCK_AUTH_USER hook (P1.1.3).

Decision tree (top wins): STREAMLIT_ENV=prod ignores MOCK_AUTH_USER
(safety net); else MOCK_AUTH_USER -> synthetic ephemeral user; else a
logged-in ``st.user`` upserts the store once per session and caches
on ``session_state``; else ``None``.

``st`` / ``_st_runtime_exists`` degrade to ``None`` / ``lambda: False``
when Streamlit isn't installed so unit tests can monkey-patch them.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone

from auth.user import InMemoryUserStore, User, UserStore

try:
    import streamlit as st  # type: ignore
    from streamlit.runtime import exists as _st_runtime_exists  # type: ignore
except ImportError:  # pragma: no cover - exercised via monkeypatch in tests
    st = None
    _st_runtime_exists = lambda: False  # noqa: E731


_USER_STORE: UserStore = InMemoryUserStore()
_SESSION_CACHE_KEY = "_auth_user"


def get_user_store() -> UserStore:
    """Return the module-level :class:`UserStore` singleton."""
    return _USER_STORE


def set_user_store(store: UserStore) -> None:
    """Install a :class:`UserStore` (dep-injection for boot + tests)."""
    global _USER_STORE
    _USER_STORE = store


def clear_cached_user() -> None:
    """Drop the per-session cached user (used on sign-out by Task 4)."""
    if st is not None and _st_runtime_exists():
        try:
            st.session_state.pop(_SESSION_CACHE_KEY, None)
        except Exception:  # pragma: no cover - defensive
            pass


def current_user() -> User | None:
    """Resolve the current user for this render pass (cheap, memoised)."""
    if _is_prod():
        return _user_from_streamlit()
    return _mock_user_from_env() or _user_from_streamlit()


def _is_prod() -> bool:
    return os.environ.get("STREAMLIT_ENV", "").lower() == "prod"


def _mock_user_from_env() -> User | None:
    email = os.environ.get("MOCK_AUTH_USER", "").strip()
    if not email:
        return None
    sub = f"mock:{hashlib.sha256(email.encode()).hexdigest()[:16]}"
    now = datetime.now(timezone.utc)
    return User(
        sub=sub,
        email=email,
        name=email.split("@")[0].title(),
        picture_url=None,
        created_at=now,
        updated_at=now,
    )


def _user_from_streamlit() -> User | None:
    if st is None or not _st_runtime_exists():
        return None

    cached = _cache_get()
    if cached is not None:
        return cached

    st_user = getattr(st, "user", None)
    if st_user is None or not getattr(st_user, "is_logged_in", False):
        return None
    email = getattr(st_user, "email", None)
    if not email:
        return None

    # Streamlit's ``st.user`` exposes ``.sub`` for OIDC providers that
    # surface it (Google does). Fall back to email when absent — stable
    # but weaker; revisit if we ever add a non-sub provider.
    sub = getattr(st_user, "sub", None) or email
    claims = {
        "sub": sub,
        "email": email,
        "name": getattr(st_user, "name", "") or "",
        "picture": getattr(st_user, "picture", None),
    }
    user = _USER_STORE.upsert_from_oidc_claims(claims)
    _cache_set(user)
    return user


def _cache_get() -> User | None:
    try:
        return st.session_state.get(_SESSION_CACHE_KEY)
    except Exception:  # pragma: no cover - defensive
        return None


def _cache_set(user: User) -> None:
    try:
        st.session_state[_SESSION_CACHE_KEY] = user
    except Exception:  # pragma: no cover - defensive
        pass
