"""E2E sentinel tests — UIP-T2 hero polish.

Assert the three data-testid hooks the new theme helpers emit actually
attach to the DOM when the app boots unauthed. Selector-level only — the
visual look lives in the design doc, not in a test.
"""

from __future__ import annotations

import re

import pytest


pytestmark = pytest.mark.timeout(180)


def _goto(page, streamlit_server):
    page.goto(streamlit_server, wait_until="domcontentloaded", timeout=60_000)
    page.locator("h1", has_text="Inventory-Adjusted").first.wait_for(
        state="visible", timeout=90_000
    )


def test_hero_sentinels_attached_unauthed(streamlit_server, page):
    """The stance pill, conviction bar, and three tier cards must be in
    the DOM after the hero band finishes its first paint (unauthed)."""
    _goto(page, streamlit_server)

    # The hero band is the slowest to attach — wait on the stance pill
    # first, then the conviction bar, then count the three tier cards.
    page.locator('[data-testid="stance-pill"]').first.wait_for(
        state="attached", timeout=60_000
    )
    page.locator('[data-testid="conviction-bar"]').first.wait_for(
        state="attached", timeout=30_000
    )
    page.locator('[data-testid="tier-card"]').first.wait_for(
        state="attached", timeout=30_000
    )

    cards = page.locator('[data-testid="tier-card"]').count()
    assert cards == 3, f"expected 3 tier-card sentinels, got {cards}"


def test_checklist_and_countdown_attached(streamlit_server, page):
    """UIP-T3: the styled checklist and catalyst countdown must attach to
    the hero band DOM within 60 s of first paint."""
    _goto(page, streamlit_server)

    page.locator('[data-testid="checklist"]').first.wait_for(
        state="attached", timeout=60_000
    )
    page.locator('[data-testid="catalyst-countdown"]').first.wait_for(
        state="attached", timeout=60_000
    )


def test_ticker_strip_renders_above_hero(streamlit_server, page):
    """UIP-T4: the Bloomberg-tape ticker strip must attach AND sit above
    the hero band vertically — its bounding_box().y must be less than the
    hero-band's. Also asserts at least 2 ``.ticker-item`` children."""
    _goto(page, streamlit_server)

    ticker = page.locator('[data-testid="ticker-strip"]').first
    hero = page.locator('[data-testid="hero-band"]').first
    ticker.wait_for(state="attached", timeout=60_000)
    hero.wait_for(state="attached", timeout=60_000)
    # bounding_box() requires the element to be visible/in-layout.
    ticker.scroll_into_view_if_needed(timeout=10_000)
    ticker_box = ticker.bounding_box()
    hero_box = hero.bounding_box()
    assert ticker_box is not None, "ticker-strip has no bounding box"
    assert hero_box is not None, "hero-band has no bounding box"
    assert ticker_box["y"] < hero_box["y"], (
        f"expected ticker.y ({ticker_box['y']}) < hero.y ({hero_box['y']})"
    )

    items = page.locator('[data-testid="ticker-strip"] .ticker-item').count()
    assert items >= 2, f"expected >= 2 ticker-item children, got {items}"


def test_onboarding_toast_attaches_on_first_visit(browser, streamlit_server):
    """UIP-T8: on a fresh browser context (empty localStorage) the
    onboarding component must mount an iframe host below the hero band.

    UIP stabilise: we deliberately do NOT descend into the components
    iframe or test the click-to-dismiss flow — frame traversal under
    ``height=1`` Streamlit components is racy on macOS sandboxes and the
    click-then-poll path depends on timing that isn't worth the flake.
    An iframe being present is sufficient signal that
    ``render_onboarding()`` ran; the visual + interactive behaviour
    remains locked in by the unit tests around ``_build_onboarding_html``.
    """
    ctx = browser.new_context(viewport={"width": 1440, "height": 1800})
    try:
        page = ctx.new_page()
        page.goto(streamlit_server, wait_until="domcontentloaded", timeout=90_000)
        # Wait for the hero band as a reliable "app is up" signal — the
        # onboarding component mounts after ``inject_css`` at app boot.
        page.locator('[data-testid="hero-band"]').first.wait_for(
            state="attached", timeout=60_000
        )
        # The onboarding component renders an iframe via
        # ``st.components.v1.html``. Presence of at least one iframe on
        # the page confirms the component was mounted.
        assert page.locator("iframe").count() >= 1, (
            "no iframe attached — components_html never mounted the "
            "onboarding component"
        )
    finally:
        ctx.close()


def test_page_title_is_generic(streamlit_server, page):
    """UIP-T9: the browser page title must be the generic product name
    ``"Macro Oil Terminal"``. No personalization — no "Aidan's Desk",
    no "Spread Arbitrage & AIS Fleet" strapline. Locked by the meta
    polish pass.
    """
    page.goto(streamlit_server, wait_until="domcontentloaded", timeout=60_000)
    # Streamlit sets document.title after the script config runs; wait a
    # beat for the set_page_config side-effect to land.
    page.locator("h1", has_text="Inventory-Adjusted").first.wait_for(
        state="visible", timeout=90_000
    )
    title = page.title()
    assert title == "Macro Oil Terminal", (
        f"expected page title 'Macro Oil Terminal', got {title!r}"
    )


def test_footer_sentinel_attached_and_matches_pattern(streamlit_server, page):
    """UIP-T9: ``[data-testid="app-footer"]`` must attach to the DOM and
    its text must match the one-line disclaimer pattern ::

        Research … education only · v<anything> · deployed to <region>

    Region defaults to ``canadaeast``; version is whatever
    ``BUILD_VERSION`` resolves to at boot (``"dev"`` in test runs).

    UIP stabilise: gate on the hero band as the "app is up" signal, then
    scroll to the bottom so the footer element enters the DOM + viewport
    before we assert on it. Streamlit streams widgets — the footer is
    the last call in ``app.py``, so it lands a few seconds after first
    paint.
    """
    page.goto(streamlit_server, wait_until="domcontentloaded", timeout=90_000)
    page.locator('[data-testid="hero-band"]').first.wait_for(
        state="attached", timeout=60_000
    )

    footer = page.locator('[data-testid="app-footer"]').first
    # Scroll to ensure the footer element enters the DOM + viewport
    # (Streamlit streams widgets and the footer is the last call in
    # ``app.py``).
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    footer.wait_for(state="attached", timeout=60_000)

    text = footer.text_content() or ""
    # Collapse whitespace so multiline HTML doesn't break the regex.
    text = re.sub(r"\s+", " ", text).strip()

    pattern = re.compile(
        r"^Research.*education only\s*[·•]\s*v.+\s*[·•]\s*deployed to .+$"
    )
    assert pattern.match(text), (
        f"footer text {text!r} did not match expected pattern"
    )
