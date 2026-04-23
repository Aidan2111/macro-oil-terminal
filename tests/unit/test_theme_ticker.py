"""Unit tests for ``theme.render_ticker_strip`` — UIP-T4.

See ``docs/plans/ui-polish.md`` → Task T4 for the contract locked in
here. The helper renders a single ``<div class="ticker-strip">`` with
one ``<div class="ticker-item">`` child per quote dict, each carrying:

* a symbol label (``display_name`` or raw ``symbol``),
* a price formatted ``$X,XXX.XX`` (thousands separator, two decimals),
* a delta line ``+X.XX (+X.XX%)`` (always-signed),
* an inline SVG sparkline (80x24 viewBox) drawn as a polyline min-max
  scaled into ``y ∈ [2, 22]`` — skipped entirely when the values list
  is empty / None.

Color logic:
* ``delta_pct > 0`` → PALETTE.positive (#84CC16)
* ``delta_pct < 0`` → PALETTE.negative (#F43F5E)
* ``delta_pct == 0`` → PALETTE.text_secondary (#9AA4B8)

All rendering goes through a single ``st.markdown(unsafe_allow_html=True)``
call, which the tests capture via monkeypatch.
"""

from __future__ import annotations

import pytest

import theme
from theme import render_ticker_strip


# ---------------------------------------------------------------------------
# Capture helper — mirrors the pattern used by test_theme_hero.py and
# test_theme_checklist_countdown.py so this file plays nicely with the
# rest of the theme suite.
# ---------------------------------------------------------------------------
def _capture_markdown(monkeypatch):
    calls: list[tuple[str, bool]] = []

    def _fake_markdown(body, unsafe_allow_html=False):
        calls.append((body, bool(unsafe_allow_html)))

    monkeypatch.setattr("theme.st.markdown", _fake_markdown)
    return calls


def _make_quote(**kwargs) -> dict:
    """Build a quote dict with sensible defaults, overridden by kwargs."""
    base = {
        "symbol": "BZ=F",
        "display_name": "Brent",
        "price": 82.14,
        "delta_abs": 0.43,
        "delta_pct": 0.52,
        "sparkline_values": [80.0, 80.5, 81.0, 81.8, 82.14],
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# 1. One .ticker-item per quote + one data-symbol per quote
# ---------------------------------------------------------------------------
def test_render_ticker_strip_emits_one_item_per_quote(monkeypatch):
    """Four quotes must produce exactly four ``.ticker-item`` blocks and
    four ``data-symbol="..."`` attributes — one per quote."""
    calls = _capture_markdown(monkeypatch)
    quotes = [
        _make_quote(symbol="BZ=F", display_name="Brent", price=82.14),
        _make_quote(symbol="CL=F", display_name="WTI", price=78.90),
        _make_quote(symbol="HO=F", display_name="Heating Oil", price=2.50),
        _make_quote(symbol="RB=F", display_name="RBOB", price=2.25),
    ]
    render_ticker_strip(quotes)
    html = "".join(body for body, _ in calls)

    assert 'data-testid="ticker-strip"' in html
    assert html.count('class="ticker-item"') == 4
    assert html.count('data-symbol="') == 4
    assert 'data-symbol="BZ=F"' in html
    assert 'data-symbol="CL=F"' in html
    assert 'data-symbol="HO=F"' in html
    assert 'data-symbol="RB=F"' in html


# ---------------------------------------------------------------------------
# 2. Positive delta → positive palette color on both delta text + SVG stroke
# ---------------------------------------------------------------------------
def test_ticker_sparkline_uses_delta_color_positive(monkeypatch):
    """``delta_pct > 0`` must paint both the delta label and the polyline
    stroke in ``PALETTE.positive`` (#84CC16)."""
    calls = _capture_markdown(monkeypatch)
    quote = _make_quote(
        delta_abs=0.43,
        delta_pct=1.5,
        sparkline_values=[80.0, 81.0, 82.0, 82.5, 83.0],
    )
    render_ticker_strip([quote])
    html = "".join(body for body, _ in calls)

    assert "#84CC16" in html
    assert '<polyline' in html
    assert 'stroke="#84CC16"' in html


# ---------------------------------------------------------------------------
# 3. Negative delta → negative palette color
# ---------------------------------------------------------------------------
def test_ticker_sparkline_uses_delta_color_negative(monkeypatch):
    """``delta_pct < 0`` must paint both the delta label and the polyline
    stroke in ``PALETTE.negative`` (#F43F5E)."""
    calls = _capture_markdown(monkeypatch)
    quote = _make_quote(
        delta_abs=-0.67,
        delta_pct=-0.8,
        sparkline_values=[83.0, 82.5, 82.0, 81.6, 82.3],
    )
    render_ticker_strip([quote])
    html = "".join(body for body, _ in calls)

    assert "#F43F5E" in html
    assert 'stroke="#F43F5E"' in html


# ---------------------------------------------------------------------------
# 4. Empty sparkline → no <svg>, but item still renders with symbol/price/delta
# ---------------------------------------------------------------------------
def test_ticker_handles_empty_sparkline_gracefully(monkeypatch):
    """``sparkline_values=[]`` should elide the SVG element; the item's
    symbol, price, and delta must still render."""
    calls = _capture_markdown(monkeypatch)
    quote = _make_quote(
        symbol="BZ=F",
        display_name="Brent",
        price=82.14,
        delta_abs=0.43,
        delta_pct=0.52,
        sparkline_values=[],
    )
    render_ticker_strip([quote])
    html = "".join(body for body, _ in calls)

    # No SVG element at all for this item.
    assert "<svg" not in html
    assert "<polyline" not in html
    # But the symbol/price/delta content still renders.
    assert "Brent" in html
    assert "$82.14" in html
    assert "+0.43" in html


# ---------------------------------------------------------------------------
# 5. Price formatting — thousands comma + two decimals
# ---------------------------------------------------------------------------
def test_ticker_price_formatted_with_commas_and_two_decimals(monkeypatch):
    """A price of 82143.7 must render as ``$82,143.70``."""
    calls = _capture_markdown(monkeypatch)
    quote = _make_quote(price=82143.7)
    render_ticker_strip([quote])
    html = "".join(body for body, _ in calls)

    assert "$82,143.70" in html


# ---------------------------------------------------------------------------
# 6. Delta formatting — always-signed absolute + always-signed percent
# ---------------------------------------------------------------------------
def test_ticker_delta_shows_sign(monkeypatch):
    """Positive delta must render as ``+0.43 (+0.52%)``; negative must
    render as ``-1.20 (-1.44%)``. Both signs always shown."""
    calls_pos = _capture_markdown(monkeypatch)
    render_ticker_strip([_make_quote(delta_abs=0.43, delta_pct=0.52)])
    html_pos = "".join(body for body, _ in calls_pos)
    assert "+0.43 (+0.52%)" in html_pos

    calls_neg = _capture_markdown(monkeypatch)
    render_ticker_strip([_make_quote(delta_abs=-1.20, delta_pct=-1.44)])
    html_neg = "".join(body for body, _ in calls_neg)
    assert "-1.20 (-1.44%)" in html_neg
