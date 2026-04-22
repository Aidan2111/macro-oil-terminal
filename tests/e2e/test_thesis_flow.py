"""E2E coverage for the AI trade thesis flow (mode toggle, history).

Runs offline: the app's rule-based fallback kicks in when AZURE_OPENAI_*
env vars are missing, so these tests assert on behaviour, not live
model output.
"""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.timeout(120)


def _goto_ai(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    page.locator("h1", has_text="Inventory-Adjusted").first.wait_for(state="visible", timeout=90_000)
    page.get_by_role("tab", name="AI trade thesis").first.wait_for(state="visible", timeout=90_000)
    page.get_by_role("tab", name="AI trade thesis").click()
    # Wait for the tab panel content to render (rate-limit caption is a stable sentinel)
    page.wait_for_selector("text=Requests this hour", timeout=60_000)


def test_mode_toggle_visible(streamlit_server, page):
    _goto_ai(page, streamlit_server)
    # Both mode labels visible
    body = page.inner_text("body")
    assert "gpt-4o" in body
    assert "o4-mini" in body


def test_regenerate_button_present(streamlit_server, page):
    _goto_ai(page, streamlit_server)
    # Streamlit buttons render as <button>; the primary CTA is labelled Regenerate
    assert page.get_by_role("button", name="Regenerate").count() >= 1


def test_recent_theses_expander_exists(streamlit_server, page):
    _goto_ai(page, streamlit_server)
    body = page.inner_text("body")
    # The expander label contains "Recent theses" regardless of count
    assert "Recent theses" in body


def test_data_caveats_expander(streamlit_server, page):
    _goto_ai(page, streamlit_server)
    body = page.inner_text("body")
    assert "Things to keep in mind" in body


def test_disclaimer_footer(streamlit_server, page):
    _goto_ai(page, streamlit_server)
    body = page.inner_text("body")
    assert "Research / education only" in body


def test_context_expander_shows_json(streamlit_server, page):
    _goto_ai(page, streamlit_server)
    # Click the "Context sent to the model" expander
    page.get_by_text("Context sent to the model").click()
    page.wait_for_selector("text=latest_brent", timeout=15_000)
