"""E2E test for hero thesis band (Task 6/6)."""

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.timeout(180)


def _wait_for_app(page, streamlit_server):
    page.goto(streamlit_server, wait_until="domcontentloaded", timeout=60_000)
    page.locator("h1", has_text="Inventory-Adjusted").first.wait_for(
        state="visible", timeout=90_000
    )
    # Streamlit renders the tab-list a moment after the main script finishes.
    # Wait for it so subsequent get_by_role('tab', ...) calls don't race.
    page.locator('[data-baseweb="tab-list"]').first.wait_for(
        state="visible", timeout=60_000
    )


def test_hero_band_renders_above_tabs(streamlit_server, page):
    _wait_for_app(page, streamlit_server)
    hero = page.locator('[data-testid="hero-band"]').first
    hero.wait_for(state="visible", timeout=30_000)
    expect(hero).to_be_visible()

    tabs = page.locator('[data-baseweb="tab-list"]').first
    expect(tabs).to_be_visible()

    hero_box = hero.bounding_box()
    tabs_box = tabs.bounding_box()
    assert hero_box is not None and tabs_box is not None
    assert hero_box["y"] + hero_box["height"] <= tabs_box["y"] + 5, (
        f"hero bottom {hero_box['y']+hero_box['height']} must be at or above "
        f"tabs top {tabs_box['y']}"
    )


def test_ai_insights_tab_is_gone(streamlit_server, page):
    _wait_for_app(page, streamlit_server)
    # Wait for each remaining tab to actually attach to the DOM before
    # asserting. Streamlit renders tabs asynchronously after the tab-list.
    for name in ("Spread dislocation", "Inventory drawdown", "Tanker fleet"):
        page.get_by_role("tab", name=name).first.wait_for(
            state="attached", timeout=60_000
        )
    # The old tab is gone
    ai_tab = page.get_by_role("tab", name="AI trade thesis")
    assert ai_tab.count() == 0, "AI Insights tab must be removed in Task 6c"
    # Three remaining tabs still present
    for name in ("Spread dislocation", "Inventory drawdown", "Tanker fleet"):
        assert page.get_by_role("tab", name=name).count() >= 1


def test_hero_disclaimer_renders(streamlit_server, page):
    _wait_for_app(page, streamlit_server)
    # Wait for the hero band to render before reading body text — the
    # disclaimer caption sits at the bottom of the hero body and only
    # appears after the thesis has been generated.
    page.locator('[data-testid="hero-band"]').first.wait_for(
        state="visible", timeout=30_000
    )
    page.wait_for_selector("text=Research & education only", timeout=30_000)
    body = page.inner_text("body")
    assert "Research & education only" in body
    assert "15-min delayed" in body


def test_hero_portfolio_input_default_100k(streamlit_server, page):
    _wait_for_app(page, streamlit_server)
    # Streamlit number_input is an <input type="number"> with the label as aria
    inp = page.get_by_role("spinbutton", name="Portfolio (USD)").first
    inp.wait_for(state="visible", timeout=15_000)
    # The value attribute on load is the default (100000)
    value = inp.input_value()
    assert value in ("100000", "100000.00", "100,000")
