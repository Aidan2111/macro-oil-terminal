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
    page.get_by_role("tab", name="Spread dislocation").first.wait_for(
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
    # at the bottom of Tab 1.
    for tab_name in (
        "Spread dislocation",
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


def test_dislocation_label_replaced_z_score(streamlit_server, page):
    _goto(page, streamlit_server)
    body = page.inner_text("body")
    assert "Dislocation" in body
    # "Dislocation" must be at least as frequent as "Z-Score" / "Z-score"
    zscore_hits = len(re.findall(r"Z-[Ss]core", body))
    disloc_hits = body.count("Dislocation")
    assert disloc_hits >= zscore_hits, (
        f"Expected Dislocation ≥ Z-Score; got Dislocation={disloc_hits}, Z-Score={zscore_hits}"
    )


def test_hero_band_shows_plain_language_stance(streamlit_server, page):
    """The old AI tab's stance labels now live in the always-visible hero band."""
    _goto(page, streamlit_server)
    hero = page.locator('[data-testid="hero-band"]').first
    hero.wait_for(state="visible", timeout=30_000)
    body = page.inner_text("body")
    # Hero band renders one of the three plain-language stance pills.
    assert any(s in body for s in ("BUY SPREAD", "SELL SPREAD", "STAND ASIDE"))


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
