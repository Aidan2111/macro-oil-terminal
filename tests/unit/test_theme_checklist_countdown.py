"""Unit tests for ``theme`` T3 helpers — styled checklist + catalyst
countdown (UIP-T3).

See ``docs/plans/ui-polish.md`` → Task T3 for the contract these tests
lock in. The checklist helper reads ``ChecklistItem.auto_check`` —
``True`` means satisfied, ``False``/``None`` means not satisfied. The
countdown helper accepts ``float | None`` hours and renders either
``"⏱ EIA release in Xd Yh"`` (primary color) or the neutral
``"No scheduled catalyst"`` sentinel.

Rounding note: the countdown uses Python's built-in ``round()`` for the
hours component, which is banker's rounding. 14.5 → 14, not 15. Locked
in here so T5/T6 charts can match.
"""

from __future__ import annotations

import pytest

import theme
from theme import render_catalyst_countdown, render_checklist
from trade_thesis import ChecklistItem


# ---------------------------------------------------------------------------
# Capture helper — collect every (body, unsafe_allow_html) pair written
# via st.markdown so each test can assert against the joined HTML blob.
# ---------------------------------------------------------------------------
def _capture_markdown(monkeypatch):
    calls: list[tuple[str, bool]] = []

    def _fake_markdown(body, unsafe_allow_html=False):
        calls.append((body, bool(unsafe_allow_html)))

    monkeypatch.setattr("theme.st.markdown", _fake_markdown)
    return calls


# ---------------------------------------------------------------------------
# 1. render_checklist — <ul> wrapper + one <li> per item + data-checked attrs
# ---------------------------------------------------------------------------
def test_render_checklist_emits_styled_list(monkeypatch):
    """Two items — one auto_check=True, one auto_check=False — must emit
    a single ``<ul class="checklist" data-testid="checklist">`` wrapping
    two ``<li class="checklist-item"`` entries with matching
    ``data-checked`` values. Both labels must render in the output HTML.
    """
    calls = _capture_markdown(monkeypatch)
    items = [
        ChecklistItem("catalyst_clear", "No EIA release within 24h.", True),
        ChecklistItem("stop_in_place", "I have a stop at 2-sigma.", False),
    ]
    render_checklist(items)
    html = "".join(body for body, _ in calls)

    assert '<ul class="checklist" data-testid="checklist"' in html
    # Exactly two <li class="checklist-item" entries.
    assert html.count('<li class="checklist-item"') == 2
    assert 'data-checked="true"' in html
    assert 'data-checked="false"' in html
    assert "No EIA release within 24h." in html
    assert "I have a stop at 2-sigma." in html


# ---------------------------------------------------------------------------
# 2. render_checklist — Lucide SVG content for checked vs unchecked
# ---------------------------------------------------------------------------
def test_render_checklist_uses_check_circle_svg_for_checked(monkeypatch):
    """Checked rows must carry the Lucide ``check-circle`` path
    (``M22 11.08V12``); unchecked rows must carry the bare ``circle``
    element. Both SVGs must appear when the list mixes states.
    """
    calls = _capture_markdown(monkeypatch)
    items = [
        ChecklistItem("a", "label a", True),
        ChecklistItem("b", "label b", None),
    ]
    render_checklist(items)
    html = "".join(body for body, _ in calls)

    # Lucide check-circle signature path (from brainstorm doc).
    assert 'd="M22 11.08V12' in html
    # Lucide plain circle signature — the checked row's path also contains
    # a circle? No — the check-circle svg uses path + polyline, not
    # <circle>, so this uniquely identifies the unchecked row's svg.
    assert 'circle cx="12"' in html


# ---------------------------------------------------------------------------
# 3. render_catalyst_countdown — days + hours formatting across edge cases
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "hours, expected_fragment",
    [
        # 62.5 h → 2d + 14.5 h. round(14.5) == 14 (banker's rounding).
        (62.5, "2d 14h"),
        (5.0, "0d 5h"),
        (0.4, "0d 0h"),
        (48.0, "2d 0h"),
        (None, "No scheduled catalyst"),
        (-1.0, "No scheduled catalyst"),
    ],
)
def test_render_catalyst_countdown_formats_days_hours(monkeypatch, hours, expected_fragment):
    """Parametrised formatting contract. ``None`` and negative hours both
    render the neutral sentinel; positive hours render
    ``"EIA release in Xd Yh"`` with banker's rounding on the hour remainder.
    """
    calls = _capture_markdown(monkeypatch)
    render_catalyst_countdown(hours)
    html = "".join(body for body, _ in calls)
    assert expected_fragment in html
    # Always carry the data-testid so the e2e sentinel can resolve.
    assert 'data-testid="catalyst-countdown"' in html


# ---------------------------------------------------------------------------
# 4. render_catalyst_countdown — primary color only when a future catalyst
# ---------------------------------------------------------------------------
def test_render_catalyst_countdown_uses_primary_color_for_future(monkeypatch):
    """Future countdown must tint with ``PALETTE.primary`` (#22D3EE).
    ``None`` / past values fall back to the secondary text token and
    must NOT carry the primary hex.
    """
    calls_future = _capture_markdown(monkeypatch)
    render_catalyst_countdown(12.0)
    html_future = "".join(body for body, _ in calls_future)
    assert "#22D3EE" in html_future

    # Reset and render the None sentinel.
    calls_none: list[tuple[str, bool]] = []

    def _fake_markdown_none(body, unsafe_allow_html=False):
        calls_none.append((body, bool(unsafe_allow_html)))

    monkeypatch.setattr("theme.st.markdown", _fake_markdown_none)
    render_catalyst_countdown(None)
    html_none = "".join(body for body, _ in calls_none)
    assert "#22D3EE" not in html_none
