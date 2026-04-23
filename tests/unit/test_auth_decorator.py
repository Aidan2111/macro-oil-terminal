"""Unit tests for @requires_auth + render_login_gate (P1.1.4)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from auth import User
from auth import widgets as auth_widgets
from auth.widgets import _LOGIN_GATE_PROMPT, render_login_gate, requires_auth


def _fake_user() -> User:
    now = datetime.now(timezone.utc)
    return User(
        sub="mock:abc",
        email="trader@example.com",
        name="Trader",
        picture_url=None,
        created_at=now,
        updated_at=now,
    )


def test_requires_auth_passes_through_when_authed(monkeypatch: pytest.MonkeyPatch) -> None:
    """An authed current_user() lets the wrapped function run and return."""
    monkeypatch.setattr("auth.widgets.current_user", lambda: _fake_user())
    # render_login_gate should never fire in this path; swap it for a sentinel.
    mock_gate = MagicMock()
    monkeypatch.setattr("auth.widgets.render_login_gate", mock_gate)

    @requires_auth
    def _render() -> str:
        return "ran"

    assert _render() == "ran"
    mock_gate.assert_not_called()


def test_requires_auth_gates_when_unauthed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unauthed call skips the wrapped function and triggers the gate."""
    monkeypatch.setattr("auth.widgets.current_user", lambda: None)
    mock_gate = MagicMock()
    monkeypatch.setattr("auth.widgets.render_login_gate", mock_gate)

    side_effect: list[str] = []

    @requires_auth
    def _render() -> str:
        side_effect.append("ran")
        return "ran"

    result = _render()

    assert result is None
    assert side_effect == []
    mock_gate.assert_called_once()


def test_render_login_gate_is_noop_outside_streamlit_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a live streamlit runtime, the gate renders nothing and returns None."""
    monkeypatch.setattr(auth_widgets, "_st_runtime_exists", lambda: False)
    assert render_login_gate() is None


def test_login_gate_prompt_contains_tos_and_risk_links() -> None:
    """P1.9 compliance targets: Terms + Risk Disclosure must both be linked."""
    assert "/legal/terms" in _LOGIN_GATE_PROMPT
    assert "/legal/risk" in _LOGIN_GATE_PROMPT
