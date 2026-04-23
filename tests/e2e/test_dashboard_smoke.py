"""End-to-end smoke coverage for the terminal dashboard.

Boots a headless Streamlit, drives it with Playwright, asserts the
big-picture UI contracts are kept. No live LLM calls — the AI insights
card exercises the rule-based fallback path.
"""

from __future__ import annotations

import re

import pytest


pytestmark = pytest.mark.timeout(180)


def _goto(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    page.locator("h1", has_text="Inventory-Adjusted").first.wait_for(
        state="visible", timeout=90_000
    )
    # Streamlit renders tabs after the main script finishes; wait for one.
    # UIP-T0: tab renamed "Spread dislocation" -> "Spread Stretch".
    page.get_by_role("tab", name="Spread Stretch").first.wait_for(
        state="visible", timeout=90_000
    )


def test_title_and_header_visible(streamlit_server, page):
    _goto(page, streamlit_server)
    # The headline h1 is always rendered at the top of the main column
    assert page.locator("h1", has_text="Inventory-Adjusted").count() >= 1


def test_all_three_tabs_render(streamlit_server, page):
    _goto(page, streamlit_server)
    # The fourth "AI trade thesis" tab was retired in Task 6c — its content
    # now lives in the always-visible hero band + a Model-internals expander
    # at the bottom of Tab 1. UIP-T0 renamed Tab 1 -> "Spread Stretch".
    for tab_name in (
        "Spread Stretch",
        "Inventory drawdown",
        "Tanker fleet",
    ):
        # Wait for each tab to actually attach to the DOM before asserting.
        page.get_by_role("tab", name=tab_name).first.wait_for(
            state="attached", timeout=60_000
        )
        assert page.get_by_role("tab", name=tab_name).count() >= 1, f"tab missing: {tab_name}"


def test_ticker_strip_shows_brent_and_wti(streamlit_server, page):
    _goto(page, streamlit_server)
    # The metric labels live in st.metric widgets at the top of the page
    body = page.inner_text("body")
    assert "Brent" in body and "WTI" in body


def test_stretch_label_replaced_z_score(streamlit_server, page):
    """UIP-T0: the default-view spread-stretch label should dominate Z-score."""
    _goto(page, streamlit_server)
    body = page.inner_text("body")
    # The language pass renamed "Dislocation" -> "Spread Stretch" / "stretch".
    assert ("Stretch" in body) or ("stretch" in body)
    # The plain-English label must be at least as frequent as the technical one.
    zscore_hits = len(re.findall(r"Z-[Ss]core", body))
    stretch_hits = body.count("Stretch") + body.count("stretch")
    assert stretch_hits >= zscore_hits, (
        f"Expected Stretch >= Z-Score; got Stretch={stretch_hits}, Z-Score={zscore_hits}"
    )


def test_hero_band_shows_plain_language_stance(streamlit_server, page):
    """The old AI tab's stance labels now live in the always-visible hero band.

    Phase-C Row 13 (docs/reviews/_synthesis.md) renamed stance pills
    from prescriptive "Buy / Sell / Wait" imperatives to hypothetical
    "Lean long / Lean short / Stand aside" dispositions — pairs with
    the new invalidation-risk list + amber data-caveat strip so the
    hedging copy and hedging UI read consistently.
    """
    _goto(page, streamlit_server)
    hero = page.locator('[data-testid="hero-band"]').first
    hero.wait_for(state="visible", timeout=30_000)
    body = page.inner_text("body")
    # Hero band renders one of the three plain-language stance pills.
    assert any(s in body for s in ("LEAN LONG", "LEAN SHORT", "STAND ASIDE"))


def test_model_internals_expander_exposes_mode_toggle(streamlit_server, page):
    """Model-internals expander (bottom of Tab 1) keeps the gpt-4o / o4-mini toggle."""
    _goto(page, streamlit_server)
    # Tab 1 is visible by default; expand Model internals and assert the toggle exists
    page.get_by_text("Model internals (thesis engine)").click()
    page.wait_for_selector("text=Quick read", timeout=30_000)
    body = page.inner_text("body")
    assert "gpt-4o" in body
    assert "o4-mini" in body


def test_url_query_param_roundtrip(streamlit_server, page):
    url = streamlit_server + "/?z=2.5&floor=400&window=8"
    _goto(page, url)
    # The URL state write-back happens on every rerun. After load, the
    # address should carry z/floor/window the app round-trips into/out of state.
    # Playwright normalises URL encoding; just confirm the z value is bound.
    assert "z=2.5" in page.url
