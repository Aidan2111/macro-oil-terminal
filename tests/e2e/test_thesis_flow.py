"""E2E coverage for the AI trade thesis flow after the hero-band rewrite.

As of Task 6c, the dedicated "AI trade thesis" tab is gone. The thesis
now renders in the always-visible hero band at the top of the page, with
model-engine internals (mode toggle, recent theses, reasoning summary)
behind a "Model internals" expander at the bottom of Tab 1
("Spread dislocation").

Runs offline: the app's rule-based fallback kicks in when AZURE_OPENAI_*
env vars are missing, so these tests assert on behaviour, not live
model output.
"""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.timeout(120)


def _goto(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=90_000)
    page.locator("h1", has_text="Inventory-Adjusted").first.wait_for(
        state="visible", timeout=120_000
    )
    # Hero band is the last main-column element Streamlit renders; in CI on
    # a cold Chromium the full script takes longer than on dev laptops.
    # Use the disclaimer caption as the "app is fully hydrated" sentinel —
    # it's the explicit last-render marker inside the hero band.
    page.wait_for_selector(
        'text="Research & education only"', state="visible", timeout=120_000
    )
    page.locator('[data-testid="hero-band"]').first.wait_for(
        state="visible", timeout=60_000
    )


def _open_model_internals(page):
    """Open the Model-internals expander on Tab 1 where the mode toggle now lives."""
    page.get_by_text("Model internals (thesis engine)").click()
    page.wait_for_selector("text=Quick read", timeout=60_000)


def test_mode_toggle_visible(streamlit_server, page):
    _goto(page, streamlit_server)
    _open_model_internals(page)
    body = page.inner_text("body")
    # Both mode labels visible inside the Model-internals expander
    assert "gpt-4o" in body
    assert "o4-mini" in body


def test_regenerate_button_present(streamlit_server, page):
    _goto(page, streamlit_server)
    _open_model_internals(page)
    # The primary CTA label survives the move into the expander
    assert page.get_by_role("button", name="Regenerate").count() >= 1


def test_recent_theses_expander_exists(streamlit_server, page):
    _goto(page, streamlit_server)
    _open_model_internals(page)
    body = page.inner_text("body")
    # The nested expander label contains "Recent theses" regardless of count
    assert "Recent theses" in body


def test_hero_disclaimer_footer(streamlit_server, page):
    _goto(page, streamlit_server)
    # The disclaimer caption is the last element inside the hero body;
    # wait for its text specifically before reading the full body.
    page.wait_for_selector("text=Research & education only", timeout=30_000)
    body = page.inner_text("body")
    # Hero band renders the disclaimer caption on every page load
    assert "Research & education only" in body


def test_hero_stance_pill_renders(streamlit_server, page):
    _goto(page, streamlit_server)
    body = page.inner_text("body")
    # The hero band emits one of the three plain-language stance labels.
    # UIP-T0 renamed: BUY SPREAD -> BUY THE SPREAD, SELL SPREAD -> SELL THE SPREAD,
    # STAND ASIDE -> WAIT.
    assert any(s in body for s in ("BUY THE SPREAD", "SELL THE SPREAD", "WAIT"))
