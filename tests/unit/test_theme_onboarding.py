"""Unit tests for ``theme.render_onboarding`` — first-visit onboarding
toasts (UIP-T8).

See ``docs/plans/ui-polish.md`` → Task T8 and ``docs/designs/ui-polish.md``
→ "Onboarding toasts" for the contract these tests lock in.

``render_onboarding()`` emits a small HTML+JS component once at the top of
``app.py`` via ``st.components.v1.html``. On first load (no
``localStorage["mot_onboarding_done"]`` flag) it spawns a stack of three
fixed toasts in sequence, then sets the flag so subsequent visits skip
the sequence. ESC + click-anywhere dismiss the stack.

The three messages are fixed — the generic "Macro Oil Terminal" branding
per the final copy review. No personalization (no "Aidan", no "personal
desk" wording) — a parametrised test guards that invariant.

All assertions run against the HTML string captured from a monkeypatched
``theme._components_html``. Outside a Streamlit runtime the helper is a
no-op.
"""

from __future__ import annotations

import pytest

import theme
from theme import render_onboarding


# ---------------------------------------------------------------------------
# Capture helper — mocks the st.components.v1.html entry point that the
# helper imports via ``from streamlit.components.v1 import html as
# _components_html``. Tests patch the module-level reference so the mock
# catches the call regardless of how Streamlit routes internally.
# ---------------------------------------------------------------------------
def _capture_component(monkeypatch):
    calls: list[tuple[tuple, dict]] = []

    def _fake_components_html(*args, **kwargs):
        calls.append((args, kwargs))
        return None

    monkeypatch.setattr("theme._components_html", _fake_components_html)
    return calls


def _captured_html(calls) -> str:
    """Concatenate the HTML body from every capture call."""
    parts: list[str] = []
    for args, kwargs in calls:
        if args:
            parts.append(str(args[0]))
        elif "html" in kwargs:
            parts.append(str(kwargs["html"]))
        elif "body" in kwargs:
            parts.append(str(kwargs["body"]))
    return "".join(parts)


# ---------------------------------------------------------------------------
# 1. render_onboarding emits a single non-empty HTML component
# ---------------------------------------------------------------------------
def test_render_onboarding_emits_html_component(monkeypatch):
    """One call to ``_components_html`` with a non-empty body that
    contains the toast class + data-testid sentinels."""
    calls = _capture_component(monkeypatch)

    render_onboarding()

    assert len(calls) == 1, f"expected exactly 1 components_html call, got {len(calls)}"
    html = _captured_html(calls)
    assert html, "captured HTML body is empty"
    assert "onb-toast" in html
    assert 'data-testid="onboarding-toast"' in html


# ---------------------------------------------------------------------------
# 2. All three fixed messages appear in the HTML (parametrised).
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "message",
    [
        (
            "Welcome to Macro Oil Terminal \u2014 a research desk for "
            "crude spread dislocations. Hover any metric for the math."
        ),
        (
            "The hero card is the current trade idea. Confidence tells "
            "you how strong the signal is."
        ),
        "Scroll or click the tabs for the data behind the signal.",
    ],
)
def test_onboarding_html_contains_all_three_messages(monkeypatch, message):
    """Each fixed copy string must appear verbatim in the component
    body. Copy drift → test fails → reviewer notices."""
    calls = _capture_component(monkeypatch)
    render_onboarding()
    html = _captured_html(calls)
    assert message in html, f"missing copy: {message!r}"


# ---------------------------------------------------------------------------
# 3. localStorage is read so the component can guard repeat visits.
# ---------------------------------------------------------------------------
def test_onboarding_html_reads_localstorage(monkeypatch):
    """The component must call ``localStorage.getItem("mot_onboarding_done")``
    — the flag key is part of the T8 contract."""
    calls = _capture_component(monkeypatch)
    render_onboarding()
    html = _captured_html(calls)
    assert 'localStorage.getItem("mot_onboarding_done")' in html


# ---------------------------------------------------------------------------
# 4. ESC keydown handler is wired (string-level check is enough here).
# ---------------------------------------------------------------------------
def test_onboarding_html_binds_keydown_escape(monkeypatch):
    """The JS must reference the ``Escape`` key string so users can
    dismiss the stack without reaching for the mouse."""
    calls = _capture_component(monkeypatch)
    render_onboarding()
    html = _captured_html(calls)
    assert "Escape" in html


# ---------------------------------------------------------------------------
# 5. Completing the sequence sets the done flag.
# ---------------------------------------------------------------------------
def test_onboarding_html_sets_done_flag_on_complete(monkeypatch):
    """``localStorage.setItem("mot_onboarding_done", ...)`` must appear
    in the JS so the three-toast sequence only runs once per browser."""
    calls = _capture_component(monkeypatch)
    render_onboarding()
    html = _captured_html(calls)
    assert 'localStorage.setItem("mot_onboarding_done"' in html


# ---------------------------------------------------------------------------
# 6. No-op outside a Streamlit runtime — mirrors the other T7/T2 helpers.
# ---------------------------------------------------------------------------
def test_onboarding_is_noop_outside_runtime(monkeypatch):
    """When ``theme._has_streamlit_runtime()`` returns False, the
    helper must skip the components_html call entirely."""
    calls = _capture_component(monkeypatch)
    monkeypatch.setattr(theme, "_has_streamlit_runtime", lambda: False)

    render_onboarding()

    assert calls == [], "components_html was invoked outside a runtime"


# ---------------------------------------------------------------------------
# 7. Branding invariant — no personal-name strings in the copy.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "needle",
    ["aidan", "Aidan", "Aidan's Desk", "personal"],
)
def test_onboarding_no_personal_strings(monkeypatch, needle):
    """The final T8 copy is generic 'Macro Oil Terminal' — the
    brainstorm's original "Aidan's desk" phrasing must not slip through.
    Case-insensitive substring match."""
    calls = _capture_component(monkeypatch)
    render_onboarding()
    html = _captured_html(calls)
    assert needle.lower() not in html.lower(), (
        f"forbidden personalization token {needle!r} found in onboarding HTML"
    )
