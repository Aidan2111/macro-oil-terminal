"""Auth widgets + decorators (P1.1.4).

Surfaces a tiny, compose-friendly gate used by render helpers and by
fully auth-walled pages:

* :func:`requires_auth` — decorator; runs the wrapped function only when
  :func:`auth.session.current_user` returns a user, else invokes
  :func:`render_login_gate` and short-circuits to ``None``.
* :func:`render_login_gate` — inline prompt with Terms + Risk Disclosure
  links (P1.9 targets). No-op outside a Streamlit runtime so unit tests
  don't need a live server.
* :func:`require_auth` — route-level guard: render the gate and call
  ``st.stop()`` when unauthed. Used by entirely auth-walled pages
  (onboarding, settings — wired in later P1.x tasks).

Real ``st.login("google")`` wiring lands in Task 5; the button here is
intentionally a placeholder so this module stays independent of the
1.42-era auth surface in unit tests.
"""
from __future__ import annotations

import functools
from typing import Any, Callable

from auth.session import current_user

try:
    import streamlit as st  # type: ignore
    from streamlit.runtime import exists as _st_runtime_exists  # type: ignore
except ImportError:  # pragma: no cover - exercised via monkeypatch in tests
    st = None
    _st_runtime_exists = lambda: False  # noqa: E731


_LOGIN_GATE_TOS_LINK = "/legal/terms"
_LOGIN_GATE_RISK_LINK = "/legal/risk"
_LOGIN_GATE_PROMPT = (
    "Sign in with Google to continue. "
    f"By continuing you accept our [Terms]({_LOGIN_GATE_TOS_LINK}) and "
    f"[Risk Disclosure]({_LOGIN_GATE_RISK_LINK})."
)
_SIGNIN_BUTTON_KEY = "auth-signin-gate-btn"


def _is_authed() -> bool:
    """Single source of truth for ``requires_auth`` + ``require_auth``."""
    return current_user() is not None


def render_login_gate(*, reason: str | None = None) -> None:
    """Render an inline sign-in prompt. No-op outside a streamlit runtime."""
    if st is None or not _st_runtime_exists():
        return

    st.info(reason or _LOGIN_GATE_PROMPT)
    clicked = st.button(
        "Sign in with Google",
        key=_SIGNIN_BUTTON_KEY,
        type="primary",
    )
    if clicked:
        # TODO(P1.1.6): wire real login via env-configured st.login(...).
        # Task 5 owns the real header sign-in; the gate button is a
        # placeholder so widgets stay independent of Streamlit 1.42+.
        getattr(st, "login", lambda *_: None)("google")


def requires_auth(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: only call ``fn`` when signed in; else render a login gate.

    Works outside a Streamlit runtime — ``render_login_gate`` no-ops and
    the wrapper returns ``None`` silently, which is exactly what unit
    tests want.
    """

    @functools.wraps(fn)
    def _wrapper(*args: Any, **kwargs: Any) -> Any:
        if not _is_authed():
            render_login_gate()
            return None
        return fn(*args, **kwargs)

    return _wrapper


def require_auth() -> None:
    """Route-level gate: render the login gate and ``st.stop()`` if unauthed.

    Outside a Streamlit runtime this is a no-op (tests call it freely).
    """
    if _is_authed():
        return
    render_login_gate()
    if st is not None and _st_runtime_exists():
        st.stop()
