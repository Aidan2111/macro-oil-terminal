"""E2E tests for UX revision v2 (persona 11 findings).

These assert real DOM state after Streamlit boots with the fixes landed
in theme.py / app.py:

1. Mobile sidebar-open chevron bounding box >= 44x44.
2. ``HERO &middot;`` string never appears in rendered HTML.
3. ``[data-baseweb="tab-list"]`` has ``position: sticky`` in computed
   style.
4. Streamlit ``stBaseButton-header`` has ``display: none`` (dev chrome
   hidden in prod).

Each test opens its own browser context so nothing leaks between them.
"""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.timeout(240)

MOBILE_VIEWPORT = {"width": 375, "height": 812}
DESKTOP_VIEWPORT = {"width": 1440, "height": 900}


def _mobile_page(browser, url):
    ctx = browser.new_context(viewport=MOBILE_VIEWPORT)
    page = ctx.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    page.locator("h1", has_text="Inventory-Adjusted").first.wait_for(
        state="visible", timeout=90_000
    )
    return ctx, page


def _desktop_page(browser, url):
    ctx = browser.new_context(viewport=DESKTOP_VIEWPORT)
    page = ctx.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    page.locator("h1", has_text="Inventory-Adjusted").first.wait_for(
        state="visible", timeout=90_000
    )
    return ctx, page


def test_mobile_sidebar_expand_button_is_44x44(streamlit_server, browser):
    """Persona 11 finding #3 — chevron was 28x28; must be >= 44x44."""
    ctx, page = _mobile_page(browser, streamlit_server)
    try:
        btn = page.locator(
            '[data-testid="stExpandSidebarButton"], '
            '[data-testid="stSidebarCollapsedControl"]'
        ).first
        if btn.count() == 0:
            pytest.skip("Streamlit sidebar-expand button not rendered")
        btn.wait_for(state="attached", timeout=30_000)
        bb = btn.bounding_box()
        if bb is None:
            pytest.skip("bounding box unavailable for sidebar button")
        assert bb["width"] >= 44, (
            f"sidebar-expand width {bb['width']} below 44px floor"
        )
        assert bb["height"] >= 44, (
            f"sidebar-expand height {bb['height']} below 44px floor"
        )
    finally:
        ctx.close()


def test_hero_chip_no_longer_prefixes_layout_tag(streamlit_server, browser):
    """Persona 11 finding #1 — 'HERO · ' string removed from rendered HTML."""
    ctx, page = _desktop_page(browser, streamlit_server)
    try:
        page.locator('[data-testid="hero-band"]').first.wait_for(
            state="attached", timeout=60_000
        )
        html = page.content()
        assert "HERO &middot;" not in html, (
            "rendered HTML still contains 'HERO &middot;' layout tag"
        )
        assert "HERO \u00b7" not in html, (
            "rendered HTML still contains 'HERO · ' (literal middot)"
        )
    finally:
        ctx.close()


def test_tab_list_is_position_sticky(streamlit_server, browser):
    """Persona 11 finding #6 — tab strip must be sticky so tab switches
    don't require scrolling past the hero.
    """
    ctx, page = _desktop_page(browser, streamlit_server)
    try:
        tabs = page.locator('[data-baseweb="tab-list"]').first
        tabs.wait_for(state="attached", timeout=60_000)
        position = page.evaluate(
            "(el) => window.getComputedStyle(el).position",
            tabs.element_handle(),
        )
        assert position == "sticky", (
            f"tab-list position should be 'sticky' but is {position!r}"
        )
    finally:
        ctx.close()


def test_streamlit_dev_header_button_hidden(streamlit_server, browser):
    """Persona 11 finding #5 — dev chrome (Stop / Deploy) hidden in prod."""
    ctx, page = _desktop_page(browser, streamlit_server)
    try:
        # The button may not render at all in some Streamlit versions;
        # that's a pass. If it does render, computed display must be
        # 'none'.
        header_btn = page.locator(
            'button[data-testid="stBaseButton-header"]'
        )
        if header_btn.count() == 0:
            return  # nothing to hide → pass
        display = page.evaluate(
            "(el) => window.getComputedStyle(el).display",
            header_btn.first.element_handle(),
        )
        assert display == "none", (
            f"stBaseButton-header should be hidden (display:none) but is {display!r}"
        )
    finally:
        ctx.close()
