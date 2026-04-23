"""Unit tests for ``theme`` hero helpers — stance pill, conviction bar,
tier card (UIP-T2).

See docs/plans/ui-polish.md → Task T2 for the contract these tests lock in.
"""

from __future__ import annotations

import pytest

import theme
from theme import render_stance_pill, render_conviction_bar, render_tier_card
from trade_thesis import Instrument


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
# 1. render_stance_pill — LONG_SPREAD → "LEAN LONG" + positive color
# ---------------------------------------------------------------------------
def test_render_stance_pill_emits_data_testid_and_translated_string(monkeypatch):
    """LONG_SPREAD pill must carry data-testid, translated verb, positive hex.

    Row 13 renamed "Buy the spread" → "Lean long" so the hedging copy
    reads as hypothetical rather than prescriptive. Glow opacity also
    reduced from 0x55 → 0x33 so the directional pill doesn't
    out-dramatise the hedging content below.
    """
    calls = _capture_markdown(monkeypatch)
    render_stance_pill("LONG_SPREAD")
    html = "".join(body for body, _ in calls)
    assert 'data-testid="stance-pill"' in html
    assert "LEAN LONG" in html
    assert "#84CC16" in html  # PALETTE.positive
    # Row 13 glow de-saturation — the "dramatic" 55-alpha shadow was
    # reduced to 33-alpha so hedging content below the pill holds focus.
    assert "#84CC1633" in html, "stance-pill glow must use 33-alpha, not 55"


# ---------------------------------------------------------------------------
# 2. render_stance_pill — FLAT → "STAND ASIDE" + amber warn color
# ---------------------------------------------------------------------------
def test_render_stance_pill_flat_uses_stand_aside_and_amber_color(monkeypatch):
    """FLAT pill must render 'STAND ASIDE' in the amber ``warn`` token.

    Row 13: grey was "boring" and signalled the absence of a decision.
    Amber ``PALETTE.warn`` signals active caution — the right semantic
    for a stand-aside stance.
    """
    calls = _capture_markdown(monkeypatch)
    render_stance_pill("FLAT")
    html = "".join(body for body, _ in calls)
    assert "STAND ASIDE" in html
    assert "#F59E0B" in html  # PALETTE.warn — amber, not grey


# ---------------------------------------------------------------------------
# 3. render_conviction_bar — data attributes + aria + fill width + band label
# ---------------------------------------------------------------------------
def test_render_conviction_bar_attaches_data_conviction(monkeypatch):
    """value=7 must surface as both the data attribute and aria-valuenow;
    the fill width must be 70% and the band label must say 'High'."""
    calls = _capture_markdown(monkeypatch)
    render_conviction_bar(7, "LONG_SPREAD")
    html = "".join(body for body, _ in calls)
    assert 'data-conviction="7"' in html
    assert 'aria-valuenow="7"' in html
    assert 'role="progressbar"' in html
    assert "width: 70%" in html
    assert "High" in html  # describe_confidence(7) == "High"


# ---------------------------------------------------------------------------
# 4. render_conviction_bar — out-of-range values clamp to [0, 10]
# ---------------------------------------------------------------------------
def test_render_conviction_bar_clamps_value(monkeypatch):
    """value=15 must clamp to 10 in both the data attribute and fill width."""
    calls = _capture_markdown(monkeypatch)
    render_conviction_bar(15, "FLAT")
    html = "".join(body for body, _ in calls)
    assert 'data-conviction="10"' in html
    assert "width: 100%" in html


# ---------------------------------------------------------------------------
# 5. render_tier_card — tier attribute, name, legs joiner, P&L preview prefix
# ---------------------------------------------------------------------------
def test_render_tier_card_includes_tier_attr_and_pl_label(monkeypatch):
    """Tier-2 ETF card must carry data-tier, the instrument name, the
    legs joined by ' / ', and a dollar-prefixed P&L preview stub."""
    calls = _capture_markdown(monkeypatch)
    inst = Instrument(
        tier=2,
        name="USO/BNO ETF spread",
        symbol="USO/BNO",
        rationale="long USO / short BNO",
        suggested_size_pct=5.0,
        worst_case_per_unit="~$X per $1k notional",
    )
    # Attach the legs/size_usd fields the card reads from. The Instrument
    # dataclass doesn't expose them natively; the helper falls back on
    # ``symbol`` when ``legs`` is absent — we set both to be explicit.
    inst.legs = ["USO", "BNO"]
    inst.size_usd = 50_000
    render_tier_card(inst, "tier2", "LONG_SPREAD")
    html = "".join(body for body, _ in calls)
    assert 'data-testid="tier-card"' in html
    assert 'data-tier="tier2"' in html
    assert "USO/BNO ETF spread" in html
    assert "USO / BNO" in html
    assert "$" in html  # P&L preview prefix
