"""E2E coverage for P1.1.5 header signin + auth-gated execute stub.

Three scenarios:

1. ``test_public_research_visible_without_login`` — the hero band and the
   Sign-in button both render on the unauthed root view; the signed-in
   caption is absent.
2. ``test_sign_in_button_visible_when_unauth`` — the ``data-testid``
   sentinel attaches and the visible Streamlit button reads
   "Sign in with Google" (per design spec).
3. ``test_mock_auth_unlocks_signed_in_caption`` — booting with
   ``MOCK_AUTH_USER=e2e@example.com`` + ``STREAMLIT_ENV=dev`` flips the
   header over to the signed-in caption containing that email, and the
   Sign-in sentinel is no longer present.

The sentinel divs are empty by design (Streamlit buttons don't accept
``data-testid`` directly), so we wait for ``state="attached"`` rather
than ``state="visible"`` on the sentinels themselves; the
adjacent button / caption is what asserts the visible text.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect


pytestmark = pytest.mark.timeout(180)


def _goto_root(page, base_url: str) -> None:
    page.goto(base_url, wait_until="domcontentloaded", timeout=60_000)
    # The hero band is the anchor every test below depends on.
    page.locator('[data-testid="hero-band"]').first.wait_for(
        state="visible", timeout=60_000
    )


def test_public_research_visible_without_login(streamlit_server, page):
    _goto_root(page, streamlit_server)

    # Hero band itself is the public research surface.
    hero = page.locator('[data-testid="hero-band"]').first
    expect(hero).to_be_visible()

    # The Sign-in sentinel must be attached (empty div), and the signed-in
    # caption sentinel must NOT be attached — we're unauthed.
    page.locator('[data-testid="signin-button"]').first.wait_for(
        state="attached", timeout=30_000
    )
    assert page.locator('[data-testid="signed-in-as"]').count() == 0, (
        "signed-in-as sentinel must not render in the unauthed view"
    )


def test_sign_in_button_visible_when_unauth(streamlit_server, page):
    _goto_root(page, streamlit_server)

    # The empty sentinel only confirms the code path ran; the real
    # assertion is the visible Streamlit button.
    page.locator('[data-testid="signin-button"]').first.wait_for(
        state="attached", timeout=30_000
    )
    page.get_by_role("button", name="Sign in with Google").first.wait_for(
        state="visible", timeout=60_000
    )


def test_mock_auth_unlocks_signed_in_caption(streamlit_server_mock_auth, page):
    _goto_root(page, streamlit_server_mock_auth)

    # The signed-in caption sentinel should attach; the adjacent text is
    # the visible caption.
    page.locator('[data-testid="signed-in-as"]').first.wait_for(
        state="attached", timeout=30_000
    )
    page.wait_for_selector("text=e2e@example.com", timeout=30_000)
    body = page.inner_text("body")
    assert "e2e@example.com" in body, (
        "mock-auth boot must surface the email in the header caption"
    )

    # And the Sign-in sentinel must not render.
    assert page.locator('[data-testid="signin-button"]').count() == 0, (
        "signin-button sentinel must disappear once a user is present"
    )
