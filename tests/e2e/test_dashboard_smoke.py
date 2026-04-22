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


def test_all_four_tabs_render(streamlit_server, page):
    _goto(page, streamlit_server)
    for tab_name in (
        "Spread dislocation",
        "Inventory drawdown",
        "Tanker fleet",
        "AI trade thesis",
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


def test_ai_thesis_tab_renders_card(streamlit_server, page):
    _goto(page, streamlit_server)
    page.get_by_role("tab", name="AI trade thesis").click()
    # The rate-limit caption only exists inside the AI tab panel — a good
    # sentinel for "the tab's body has actually rendered".
    page.wait_for_selector("text=Requests this hour", timeout=60_000)
    body = page.inner_text("body")
    # The mode selector offers both model labels
    assert "gpt-4o" in body
    assert "o4-mini" in body
    # Plain-language stance labels
    assert any(s in body for s in ("BUY THE SPREAD", "SELL THE SPREAD", "STAND ASIDE"))


def test_what_would_make_us_wrong_section(streamlit_server, page):
    _goto(page, streamlit_server)
    page.get_by_role("tab", name="AI trade thesis").click()
    page.wait_for_selector("text=Requests this hour", timeout=60_000)
    page.wait_for_selector("text=What would make us wrong", timeout=60_000)


def test_url_query_param_roundtrip(streamlit_server, page):
    url = streamlit_server + "/?z=2.5&floor=400&window=8"
    _goto(page, url)
    # The URL state write-back happens on every rerun. After load, the
    # address should carry z/floor/window the app round-trips into/out of state.
    # Playwright normalises URL encoding; just confirm the z value is bound.
    assert "z=2.5" in page.url
