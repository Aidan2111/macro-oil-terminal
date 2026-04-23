"""Unit tests for ``theme`` T7 helpers — loading + empty + error state
primitives (UIP-T7).

See ``docs/plans/ui-polish.md`` → Task T7 for the contract these tests
lock in. Three new helpers:

* ``render_loading_status(label, *, expanded=False)`` — context-manager
  wrapper around ``st.status``. Outside a Streamlit runtime, returns a
  no-op context manager so scripts / tests don't blow up on import.
* ``render_empty(icon, message)`` — centered empty-state card with an
  inline Lucide SVG. Valid icons: ``inbox`` / ``trending-up`` /
  ``search`` / ``alert-circle``. Unknown icon → silent fallback to
  ``inbox``.
* ``render_error(message, retry_fn=None)`` — styled error card with an
  inline ``alert-triangle`` SVG. When ``retry_fn`` is not None, an
  ``st.button("Retry now", ...)`` renders below the markdown block.

All three helpers are no-ops outside a Streamlit runtime.
"""

from __future__ import annotations

import contextlib

import pytest

import theme
from theme import render_empty, render_error, render_loading_status


# ---------------------------------------------------------------------------
# Capture helpers — mirror the pattern used across the theme test suite.
# ---------------------------------------------------------------------------
def _capture_markdown(monkeypatch):
    calls: list[tuple[str, bool]] = []

    def _fake_markdown(body, unsafe_allow_html=False):
        calls.append((body, bool(unsafe_allow_html)))

    monkeypatch.setattr("theme.st.markdown", _fake_markdown)
    return calls


def _capture_button(monkeypatch):
    """Mock ``theme.st.button`` and return the call log."""
    calls: list[tuple[tuple, dict]] = []

    def _fake_button(*args, **kwargs):
        calls.append((args, kwargs))
        return False  # button not clicked

    monkeypatch.setattr("theme.st.button", _fake_button)
    return calls


# ---------------------------------------------------------------------------
# 1. render_loading_status — returns the context manager from st.status
# ---------------------------------------------------------------------------
def test_render_loading_status_returns_context_manager(monkeypatch):
    """``render_loading_status("Hi")`` must return the same context
    manager that ``st.status`` returned. The returned object must
    support ``__enter__`` / ``__exit__`` (so the caller can use ``with
    render_loading_status(...):``)."""
    sentinel = contextlib.nullcontext("sentinel-cm")

    def _fake_status(label, **kwargs):
        assert label == "Hi"
        return sentinel

    monkeypatch.setattr("theme.st.status", _fake_status)

    cm = render_loading_status("Hi")
    assert cm is sentinel
    # And the CM interface works.
    with cm as payload:
        assert payload == "sentinel-cm"


# ---------------------------------------------------------------------------
# 2. render_loading_status — default expanded=False
# ---------------------------------------------------------------------------
def test_render_loading_status_passes_expanded_false_default(monkeypatch):
    """``render_loading_status("Fetching")`` without ``expanded`` must
    pass ``expanded=False`` through to ``st.status``. Explicitly setting
    ``expanded=True`` must propagate as well."""
    captured: list[dict] = []

    def _fake_status(label, **kwargs):
        captured.append({"label": label, **kwargs})
        return contextlib.nullcontext()

    monkeypatch.setattr("theme.st.status", _fake_status)

    render_loading_status("Fetching")
    assert captured == [{"label": "Fetching", "expanded": False}]

    captured.clear()
    render_loading_status("Loading", expanded=True)
    assert captured == [{"label": "Loading", "expanded": True}]


# ---------------------------------------------------------------------------
# 3. render_empty — sentinel + message + inbox SVG signature
# ---------------------------------------------------------------------------
def test_render_empty_emits_sentinel_and_message(monkeypatch):
    """Captured HTML must carry ``data-testid="empty-state"``, the
    message text verbatim, and a distinctive fragment of the Lucide
    ``inbox`` SVG path (the ``inbox`` icon has a polyline-approach that
    starts with ``22 12 16 12`` in Lucide's 24x24 viewBox)."""
    calls = _capture_markdown(monkeypatch)

    render_empty("inbox", "No actionable trade idea today.")
    html = "".join(body for body, _ in calls)

    assert 'data-testid="empty-state"' in html
    assert "No actionable trade idea today." in html
    # Lucide inbox SVG signature — the intake slot polyline.
    assert "22 12 16 12" in html


# ---------------------------------------------------------------------------
# 4. render_empty — unknown icon silently falls back to inbox
# ---------------------------------------------------------------------------
def test_render_empty_unknown_icon_falls_back_to_inbox(monkeypatch):
    """Passing an unknown icon name must not raise — the helper must
    silently substitute the ``inbox`` SVG so the empty-state still
    renders. Assert the inbox path fragment is present in the HTML."""
    calls = _capture_markdown(monkeypatch)

    render_empty("no_such_icon_xyz", "msg")
    html = "".join(body for body, _ in calls)

    assert 'data-testid="empty-state"' in html
    assert "msg" in html
    assert "22 12 16 12" in html  # inbox signature


# ---------------------------------------------------------------------------
# 5. render_error — sentinel + message + alert-triangle SVG signature
# ---------------------------------------------------------------------------
def test_render_error_emits_sentinel_and_message(monkeypatch):
    """Captured HTML must carry ``data-testid="error-state"``, the
    ``"Boom"`` message, and the Lucide ``alert-triangle`` signature
    path. The triangle path in Lucide 24x24 viewBox begins with
    ``M10.29 3.86``."""
    calls = _capture_markdown(monkeypatch)

    render_error("Boom")
    html = "".join(body for body, _ in calls)

    assert 'data-testid="error-state"' in html
    assert "Boom" in html
    # Lucide alert-triangle signature.
    assert "M10.29 3.86" in html


# ---------------------------------------------------------------------------
# 6. render_error — Retry button rendered when retry_fn provided
# ---------------------------------------------------------------------------
def test_render_error_renders_retry_button_when_fn_provided(monkeypatch):
    """When ``retry_fn`` is not None, ``st.button("Retry now", ...)``
    must be called exactly once after the markdown render."""
    _capture_markdown(monkeypatch)
    button_calls = _capture_button(monkeypatch)

    render_error("bad", retry_fn=lambda: None)

    assert len(button_calls) == 1
    args, kwargs = button_calls[0]
    # Button text may be passed positionally or as a kwarg.
    text = args[0] if args else kwargs.get("label")
    assert text == "Retry now"


# ---------------------------------------------------------------------------
# 7. render_error — no button when retry_fn is None
# ---------------------------------------------------------------------------
def test_render_error_skips_retry_button_when_fn_none(monkeypatch):
    """When ``retry_fn`` is None, ``st.button`` must not be invoked."""
    _capture_markdown(monkeypatch)
    button_calls = _capture_button(monkeypatch)

    render_error("bad", retry_fn=None)

    assert len(button_calls) == 0
