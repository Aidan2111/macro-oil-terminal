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
