"""E2E sentinel tests — UIP-T2 hero polish.

Assert the three data-testid hooks the new theme helpers emit actually
attach to the DOM when the app boots unauthed. Selector-level only — the
visual look lives in the design doc, not in a test.
"""

from __future__ import annotations

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
