"""Unit tests for ``theme`` — palette dataclass + CSS injection (UIP-T1).

See docs/plans/ui-polish.md → Task T1 for the contract these tests lock in.
"""

from __future__ import annotations

import dataclasses

import pytest

import theme
from theme import PALETTE, inject_css


# ---------------------------------------------------------------------------
# Test 1 — PALETTE shape
# ---------------------------------------------------------------------------
def test_palette_is_frozen_dataclass():
    """PALETTE must be an instance of a frozen dataclass."""
    assert dataclasses.is_dataclass(PALETTE)
    assert PALETTE.__dataclass_params__.frozen is True


# ---------------------------------------------------------------------------
# Test 2 — exact hex / rgba tokens (14 assertions via parametrize)
# ---------------------------------------------------------------------------
_EXPECTED_TOKENS = [
    ("bg_1", "#0A0E1A"),
    ("bg_2", "#121826"),
    ("bg_3", "#1B2232"),
    ("border", "#2A3245"),
    ("text_primary", "#E6EBF5"),
    ("text_secondary", "#9AA4B8"),
    ("text_muted", "#5B6578"),
    ("primary", "#22D3EE"),
    ("primary_glow", "rgba(34, 211, 238, 0.35)"),
    ("warn", "#F59E0B"),
    ("alert", "#EF4444"),
    ("positive", "#84CC16"),
    ("negative", "#F43F5E"),
    ("gridline", "rgba(255,255,255,0.06)"),
]


@pytest.mark.parametrize("attr,expected", _EXPECTED_TOKENS)
def test_palette_hex_tokens_match_brainstorm(attr, expected):
    """Every token listed in docs/brainstorms/ui-polish.md must match verbatim."""
    assert getattr(PALETTE, attr) == expected


# ---------------------------------------------------------------------------
# Test 3 — inject_css writes a <style> block containing every component class
# ---------------------------------------------------------------------------
def test_inject_css_writes_style_tag(monkeypatch):
    """First call must invoke st.markdown once with a <style>...</style> blob
    covering every component class the design spec requires."""
    calls = []

    def _fake_markdown(body, unsafe_allow_html=False):
        calls.append((body, unsafe_allow_html))

    fake_state = {}
    monkeypatch.setattr("theme.st.markdown", _fake_markdown)
    monkeypatch.setattr("theme.st.session_state", fake_state)

    inject_css()

    assert len(calls) == 1
    body, unsafe = calls[0]
    assert unsafe is True
    assert "<style>" in body
    assert ".stance-pill" in body
    assert ".conviction-bar" in body
    assert ".tier-card" in body
    assert "@media (max-width: 768px)" in body


# ---------------------------------------------------------------------------
# Test 4 — second call inside the same session is a no-op
# ---------------------------------------------------------------------------
def test_inject_css_is_idempotent_within_session(monkeypatch):
    """Calling inject_css twice in the same session must only write once."""

    class _Mock:
        def __init__(self):
            self.call_count = 0

        def __call__(self, body, unsafe_allow_html=False):
            self.call_count += 1

    mock = _Mock()
    fake_state = {}
    monkeypatch.setattr("theme.st.markdown", mock)
    monkeypatch.setattr("theme.st.session_state", fake_state)

    inject_css()
    inject_css()

    assert mock.call_count == 1
