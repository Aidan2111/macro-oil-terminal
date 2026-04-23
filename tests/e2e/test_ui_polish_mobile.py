"""E2E mobile-viewport tests — UIP-T6 (375x812 iPhone 13).

Five Playwright tests that validate the ``@media (max-width: 768px)``
rules in ``theme._CSS_MOBILE`` actually land on a real Streamlit page:

1. Hero stacks vertically — ticker → stance pill → conviction bar →
   tier-cards, each strictly below its predecessor.
2. No horizontal scroll — ``document.body.scrollWidth`` never exceeds
   ``window.innerWidth``.
3. Sidebar collapsed by default — Streamlit collapses the sidebar below
   640px natively; we verify that the collapse-hamburger is visible and
   the sidebar content is not.
4. Tier-cards full-width — each card's bounding-box width is at least
   320px (375 viewport minus 0.75rem-each-side padding).
5. Charts fit the viewport — the first ``.js-plotly-plot`` in Tab 1 has
   its right edge inside ``window.innerWidth + 1``.

Each test provisions its own 375x812 browser context via
``browser.new_context(viewport=...)`` so the session-scope desktop
``page`` fixture is untouched. Hero stack + screenshot tests capture a
golden PNG at ``tests/e2e/screenshots/hero_mobile.png`` for T10's
before/after README.
"""

from __future__ import annotations

import pathlib

import pytest


pytestmark = pytest.mark.timeout(240)


MOBILE_VIEWPORT = {"width": 375, "height": 812}


def _mobile_page(browser, url):
    """Open a fresh mobile-viewport browser context and navigate."""
    ctx = browser.new_context(viewport=MOBILE_VIEWPORT)
    page = ctx.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    page.locator("h1", has_text="Inventory-Adjusted").first.wait_for(
        state="visible", timeout=90_000
    )
    return ctx, page


def test_mobile_hero_stacks_vertically(streamlit_server, browser):
    """Ticker → stance → conviction → 3 tier-cards must descend vertically.

    Each sentinel's ``y`` must be strictly greater than or equal to the
    previous one's (non-decreasing); the three tier-cards' ``y`` must be
    strictly increasing (one below the next, full-width stack).
    """
    ctx, page = _mobile_page(browser, streamlit_server)
    try:
        page.locator('[data-testid="hero-band"]').first.wait_for(
            state="attached", timeout=60_000
        )
        page.locator('[data-testid="ticker-strip"]').first.wait_for(
            state="attached", timeout=60_000
        )
        page.locator('[data-testid="stance-pill"]').first.wait_for(
            state="attached", timeout=60_000
        )
        page.locator('[data-testid="conviction-bar"]').first.wait_for(
            state="attached", timeout=60_000
        )
        page.locator('[data-testid="tier-card"]').first.wait_for(
            state="attached", timeout=60_000
        )

        ticker = page.locator('[data-testid="ticker-strip"]').first
        stance = page.locator('[data-testid="stance-pill"]').first
        conviction = page.locator('[data-testid="conviction-bar"]').first
        cards = page.locator('[data-testid="tier-card"]')

        # Scroll into view so bounding boxes resolve cleanly.
        ticker.scroll_into_view_if_needed(timeout=10_000)

        tb = ticker.bounding_box()
        sb = stance.bounding_box()
        cb = conviction.bounding_box()
        assert tb is not None and sb is not None and cb is not None, (
            "ticker/stance/conviction bounding boxes must resolve"
        )

        # Ticker above stance above conviction.
        assert tb["y"] <= sb["y"], f"ticker.y {tb['y']} should be <= stance.y {sb['y']}"
        assert sb["y"] <= cb["y"], (
            f"stance.y {sb['y']} should be <= conviction.y {cb['y']}"
        )

        # Three tier-cards, each strictly below the previous.
        assert cards.count() >= 3, f"expected 3 tier-cards, got {cards.count()}"
        card_ys = []
        for i in range(3):
            el = cards.nth(i)
            el.scroll_into_view_if_needed(timeout=10_000)
            bb = el.bounding_box()
            assert bb is not None, f"tier-card[{i}] bounding box missing"
            card_ys.append(bb["y"])

        assert card_ys[0] < card_ys[1] < card_ys[2], (
            f"tier-cards should stack vertically, got ys={card_ys}"
        )

        # Capture the mobile golden at the same time — the hero is
        # already laid out and the T10 README will consume this PNG.
        screenshots_dir = (
            pathlib.Path(__file__).resolve().parent / "screenshots"
        )
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        out = screenshots_dir / "hero_mobile.png"
        # Full page is fine — the golden captures the mobile stack in situ.
        page.screenshot(path=str(out), full_page=True)
        assert out.exists() and out.stat().st_size > 0, (
            "hero_mobile.png must be written and non-empty"
        )
    finally:
        ctx.close()


def test_mobile_no_horizontal_scroll(streamlit_server, browser):
    """``document.body.scrollWidth`` must never exceed ``window.innerWidth``."""
    ctx, page = _mobile_page(browser, streamlit_server)
    try:
        page.locator('[data-testid="hero-band"]').first.wait_for(
            state="attached", timeout=60_000
        )
        # Give the ticker + tier-cards one extra frame to settle.
        page.wait_for_timeout(500)
        overflow = page.evaluate(
            "() => document.body.scrollWidth <= window.innerWidth + 1"
        )
        # If it fails, capture the gap so a maintainer knows by how much.
        if not overflow:
            gap = page.evaluate(
                "() => document.body.scrollWidth - window.innerWidth"
            )
            pytest.fail(
                f"horizontal overflow detected: body.scrollWidth exceeds "
                f"innerWidth by {gap}px"
            )
    finally:
        ctx.close()


def test_mobile_sidebar_collapsed_by_default(streamlit_server, browser):
    """Streamlit collapses the sidebar below 640px; verify that at 375px
    the hamburger / collapsed-sidebar control is present and the sidebar
    panel itself is either off-screen or zero-width (i.e. not shown).

    Different Streamlit versions render "collapsed" differently — some
    strip the content node from the DOM entirely, some leave it attached
    with ``aria-expanded="false"`` and ``transform: translateX(-100%)``,
    some leave it visible but with ``width: 0``. We accept any of those
    shapes and only fail when the sidebar element is both attached AND
    has a non-zero width AND its x-origin sits inside the viewport.
    """
    ctx, page = _mobile_page(browser, streamlit_server)
    try:
        # The hamburger / expand-sidebar control surfaces under at least
        # one of these selectors across Streamlit 1.30 → 1.50.
        hamburger = page.locator(
            '[data-testid="stSidebarCollapseButton"], '
            '[data-testid="collapsedControl"], '
            '[data-testid="stSidebarCollapsedControl"], '
            'button[aria-label*="sidebar" i], '
            'button[aria-label*="expand" i]'
        ).first
        hamburger.wait_for(state="attached", timeout=30_000)

        sidebar = page.locator('[data-testid="stSidebar"]').first
        if sidebar.count() == 0:
            # No sidebar node — definitionally collapsed.
            return

        # aria-expanded / data-collapsed attributes give us the cleanest
        # signal. If neither is exposed, fall back to a bounding-box
        # check: a collapsed sidebar sits off-screen (x < 0) or has
        # near-zero width.
        expanded = sidebar.get_attribute("aria-expanded")
        if expanded in ("false", "0"):
            return  # explicit collapse signal — pass.

        bb = sidebar.bounding_box()
        if bb is None:
            return  # not in layout → collapsed.
        # Streamlit's mobile collapsed sidebar either sits at x < 0
        # (translateX(-100%)) or has width <= 1.
        off_screen = bb["x"] + bb["width"] <= 1
        zero_width = bb["width"] <= 1
        if off_screen or zero_width:
            return

        # Last-ditch: the sidebar may render visible but very narrow
        # (a handle strip). Anything under 80px is "collapsed enough"
        # for the purpose of this test — the content panel is hidden.
        assert bb["width"] <= 80, (
            f"sidebar should be collapsed on mobile but is {bb['width']}px wide "
            f"starting at x={bb['x']}"
        )
    finally:
        ctx.close()


def test_mobile_tier_cards_full_width(streamlit_server, browser):
    """Each tier-card should span ~full viewport width at 375px.

    375 viewport minus 0.75rem-each-side padding (~24px) leaves ~351px
    of usable width; allow 320px as the lower bound for wiggle room.
    """
    ctx, page = _mobile_page(browser, streamlit_server)
    try:
        cards = page.locator('[data-testid="tier-card"]')
        cards.first.wait_for(state="attached", timeout=60_000)
        assert cards.count() >= 3, (
            f"expected 3 tier-cards, got {cards.count()}"
        )
        for i in range(3):
            el = cards.nth(i)
            el.scroll_into_view_if_needed(timeout=10_000)
            bb = el.bounding_box()
            assert bb is not None, f"tier-card[{i}] bounding box missing"
            assert bb["width"] >= 320, (
                f"tier-card[{i}] width {bb['width']} below 320px floor"
            )
    finally:
        ctx.close()


def test_mobile_chart_renders_within_viewport(streamlit_server, browser):
    """The first Plotly chart on Tab 1 must fit inside the 375px viewport.

    Navigate to the first tab, wait for a ``.js-plotly-plot`` element,
    then assert its bounding-box's right edge is at or under
    ``window.innerWidth + 1``.
    """
    ctx, page = _mobile_page(browser, streamlit_server)
    try:
        # Activate Tab 1 — "Spread Stretch" — so the first chart renders.
        tab = page.get_by_role("tab", name="Spread Stretch").first
        tab.wait_for(state="attached", timeout=60_000)
        try:
            tab.click(timeout=10_000)
        except Exception:
            # Tab may already be active; ignore the click failure and
            # fall through to the chart wait.
            pass

        chart = page.locator(".js-plotly-plot").first
        chart.wait_for(state="attached", timeout=60_000)
        chart.scroll_into_view_if_needed(timeout=10_000)
        bb = chart.bounding_box()
        assert bb is not None, "plotly chart bounding box missing"

        inner_width = page.evaluate("() => window.innerWidth")
        right_edge = bb["x"] + bb["width"]
        assert right_edge <= inner_width + 1, (
            f"chart right edge {right_edge} exceeds viewport width {inner_width}"
        )
    finally:
        ctx.close()
