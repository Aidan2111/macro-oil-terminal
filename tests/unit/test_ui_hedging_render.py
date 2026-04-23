"""Unit tests for the Phase-C Rows 2 / 5 / 13 UX hedging-layer renders.

Rows covered:
* Row 2 — render ``thesis.plain_english_headline`` as the top line of the
  hero band with ``data-testid="plain-english-headline"``.
* Row 5 — render ``thesis.invalidation_risks[:3]`` inside the hero band as
  a caption-styled list, and surface ``thesis.data_caveats`` as a
  dedicated warning strip when non-empty.
* Row 13 — stance copy rename: "Buy the spread" / "Sell the spread" /
  "Wait" become "Lean long" / "Lean short" / "Stand aside". Old strings
  must not appear anywhere in ``language.TERMS.values()``.

See ``docs/reviews/_synthesis.md`` → Rows 2, 5, 13 for the full context.

These tests are written RED first, then the implementation in
``theme.py`` / ``app.py`` / ``language.py`` is added to turn them
GREEN. The render helpers are imported lazily inside each test so
``ImportError`` during the RED phase surfaces with a readable message.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Capture helper — collect every (body, unsafe_allow_html) pair written
# via st.markdown so each test can assert against the joined HTML blob.
# Mirrors the pattern in tests/unit/test_theme_hero.py.
# ---------------------------------------------------------------------------
def _capture_markdown(monkeypatch):
    calls: list[tuple[str, bool]] = []

    def _fake_markdown(body, unsafe_allow_html=False):
        calls.append((body, bool(unsafe_allow_html)))

    monkeypatch.setattr("theme.st.markdown", _fake_markdown)
    return calls


# ---------------------------------------------------------------------------
# 1. Row 2 — plain-english headline renders when present.
# ---------------------------------------------------------------------------
def test_headline_rendered_when_present(monkeypatch):
    """The headline helper must emit the data-testid sentinel + raw text."""
    from theme import render_plain_english_headline

    calls = _capture_markdown(monkeypatch)
    render_plain_english_headline("Hello world")
    html = "".join(body for body, _ in calls)
    assert 'data-testid="plain-english-headline"' in html
    assert "Hello world" in html


# ---------------------------------------------------------------------------
# 2. Row 2 — empty / whitespace headline must not emit anything.
# ---------------------------------------------------------------------------
def test_headline_not_rendered_when_empty(monkeypatch):
    """Empty string + whitespace-only + None must all short-circuit."""
    from theme import render_plain_english_headline

    for value in ("", "   ", None):
        calls = _capture_markdown(monkeypatch)
        render_plain_english_headline(value)
        html = "".join(body for body, _ in calls)
        assert 'data-testid="plain-english-headline"' not in html, (
            f"headline helper should short-circuit on {value!r}"
        )


# ---------------------------------------------------------------------------
# 3. Row 5 — invalidations list caps at three items and carries the
#            alert-triangle glyph.
# ---------------------------------------------------------------------------
def test_render_invalidations_emits_up_to_three_items(monkeypatch):
    """Pass 5 items — the DOM must carry exactly 3 <li> rows, each with
    the Lucide alert-triangle path prefix. The parent <ul> carries the
    ``data-testid="invalidation-risks"`` sentinel."""
    from theme import render_invalidations

    calls = _capture_markdown(monkeypatch)
    render_invalidations([
        "OPEC cuts extend past Q2",
        "Cushing refill outpaces Brent loadings",
        "US dollar rally invalidates risk-on backdrop",
        "Russian discount widens past $20",
        "Refinery margin collapse removes distillate bid",
    ])
    html = "".join(body for body, _ in calls)
    assert 'data-testid="invalidation-risks"' in html
    # Exactly three <li> blocks survive the [:3] cap. Count ``<li>``
    # (with the closing ``>``) so the embedded SVG ``<line>`` elements
    # inside each alert-triangle glyph don't contaminate the count.
    assert html.count("<li>") == 3, (
        f"expected exactly 3 <li> rows, got {html.count('<li>')}; html={html!r}"
    )
    # Each row must carry the Lucide alert-triangle stroke path so the
    # caution visual is locked in (matches the triangle ``d="M10.29 3.86"``
    # prefix in the existing ``_LUCIDE_ALERT_TRIANGLE`` constant).
    assert html.count("M10.29 3.86") >= 3, (
        "each invalidation <li> must carry an alert-triangle glyph"
    )


# ---------------------------------------------------------------------------
# 4. Row 5 — caveat strip only renders when the caveats list is non-empty.
# ---------------------------------------------------------------------------
def test_render_caveat_strip_only_when_nonempty(monkeypatch):
    """Empty list must emit no HTML; one caveat must surface the string +
    amber palette token."""
    from theme import render_caveat_strip

    # Empty list — short-circuit.
    calls = _capture_markdown(monkeypatch)
    render_caveat_strip([])
    html = "".join(body for body, _ in calls)
    assert 'data-testid="data-caveats"' not in html

    # One caveat — full emit with amber var + the caveat string.
    calls = _capture_markdown(monkeypatch)
    render_caveat_strip(["Inventory feed unavailable — stance forced flat."])
    html = "".join(body for body, _ in calls)
    assert 'data-testid="data-caveats"' in html
    assert "Inventory feed unavailable" in html
    # Amber via CSS var OR the literal hex for `PALETTE.warn` — accept
    # either so the implementation has room to pick the cleaner path.
    assert ("var(--warn)" in html) or ("#F59E0B" in html), (
        "caveat strip must surface the amber warn token"
    )


# ---------------------------------------------------------------------------
# 5. Row 13 — stance copy renamed across ``language.TERMS``.
# ---------------------------------------------------------------------------
def test_terms_stance_copy_renamed():
    """The three stance display strings must read as the softer hedging
    copy. The old prescriptive strings must not appear anywhere in
    ``TERMS.values()`` so a future grep can't accidentally revert them."""
    from language import TERMS

    assert TERMS["long_spread"] == "Lean long"
    assert TERMS["short_spread"] == "Lean short"
    assert TERMS["flat"] == "Stand aside"

    joined = " | ".join(TERMS.values()).lower()
    for banned in ("buy the spread", "sell the spread"):
        assert banned not in joined, (
            f"TERMS still carries prescriptive stance copy: {banned!r}"
        )
    # "Wait" on its own is a common English word; guard against the
    # specific stance form by checking exact equality instead.
    assert "Wait" not in [TERMS["flat"]], "flat stance still reads 'Wait'"
