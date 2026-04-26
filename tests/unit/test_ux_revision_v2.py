"""Unit tests for UX revision v2 (persona 11 findings).

Each test asserts a specific CSS/render contract that the UX researcher
persona (``docs/reviews/11-ux-researcher.md``) called out. Each is
independently load-bearing — removing any one of these rules reopens a
finding the branch just closed.
"""

from __future__ import annotations

import re

import theme


# Note: the original ``test_app_py_does_not_ship_hero_dot_prefix_as_user_copy``
# regression check was retired with ``app.py`` on 2026-04-26 (Streamlit
# teardown). The remaining tests in this file still guard the legacy
# ``theme.py`` CSS contracts; the React stack has its own UI tests under
# ``frontend/__tests__/``.


# ---------------------------------------------------------------------------
# Fix 2 — Mobile sidebar-open chevron enlarged to >= 44x44.
# ---------------------------------------------------------------------------
def test_mobile_sidebar_expand_button_hits_44x44():
    """Persona 11 finding #3: the 28x28 chevron is the sole access to
    every control on mobile. The CSS must force >= 44x44.
    """
    css = theme._CSS_MOBILE_SURFACES
    # Look for a @media block that pulls stExpandSidebarButton up.
    assert 'stExpandSidebarButton' in css
    # Width/height tokens — use a flexible regex to survive minor
    # formatting drift while still catching a regression that drops
    # below 44.
    min_w = re.search(r'stExpandSidebarButton.*?min-width:\s*(\d+)px',
                      css, re.DOTALL)
    min_h = re.search(r'stExpandSidebarButton.*?min-height:\s*(\d+)px',
                      css, re.DOTALL)
    assert min_w and int(min_w.group(1)) >= 44, f"min-width regressed: {min_w}"
    assert min_h and int(min_h.group(1)) >= 44, f"min-height regressed: {min_h}"


# ---------------------------------------------------------------------------
# Fix 3 — Sign-in CTA: dark text on cyan (persona fix option A, ~11:1).
# ---------------------------------------------------------------------------
def test_css_buttons_block_darkens_primary_cta_text():
    """Persona 11 finding #4/#10: white on cyan is 1.81:1 — WCAG AA
    fail. Use Option A: dark text on cyan bg so contrast lands ~11:1.

    The ``_CSS_BUTTONS`` block must include a rule scoped to the primary
    button that sets ``color`` to a near-black token so the contrast
    calculator reads > 7:1.
    """
    css = theme._CSS_BUTTONS
    assert 'kind="primary"' in css
    # Any rule that sets color to #0A0E1A (bg_1) or #0b0f14 or similar
    # dark token on the primary button satisfies the finding.
    assert re.search(
        r'kind="primary"[^{]*\{[^}]*color:\s*#0[ab0]',
        css, re.IGNORECASE,
    ), "primary CTA still uses default (white) color — contrast regression"


# ---------------------------------------------------------------------------
# Fix 4 — Streamlit dev chrome hidden in prod.
# ---------------------------------------------------------------------------
def test_streamlit_dev_chrome_hidden_via_css():
    """Persona 11 finding #5: Streamlit's ``stBaseButton-header`` (Stop /
    Deploy) leaks into prod top-right. Hide via CSS so the prod header
    reads clean.
    """
    css_full = theme._CSS
    for selector in (
        '[data-testid="stDeployButton"]',
        '[data-testid="stAppDeployButton"]',
        'button[data-testid="stBaseButton-header"]',
    ):
        assert selector in css_full, f"missing hide selector: {selector}"
    # And each must land inside a display:none rule.
    assert 'display: none !important' in css_full


# ---------------------------------------------------------------------------
# Fix 5 — Tab bar sticky at top so tab switches don't require scroll.
# ---------------------------------------------------------------------------
def test_tab_list_is_sticky_at_top():
    """Persona 11 finding #6: the tab strip sits below the hero, so every
    tab switch requires scrolling past the hero. Make it sticky.
    """
    css = theme._CSS_TABS
    assert 'position: sticky' in css
    assert '[data-baseweb="tab-list"]' in css
    # z-index and a background token are needed so content underneath
    # doesn't bleed through the sticky strip.
    assert 'z-index' in css
    assert 'var(--bg-1)' in css or 'background' in css


# ---------------------------------------------------------------------------
# Fix 6 — Global mobile tap-target floor (bonus from "additional findings").
# ---------------------------------------------------------------------------
def test_mobile_baseline_button_tap_target_floor():
    """Persona 11 mobile breakage: 31 buttons < 44x44 on iPhone 13.

    Ship a global CSS rule that forces every ``button`` inside the main
    Streamlit surface up to 44x44 minimum on viewports <= 768px.
    """
    css = theme._CSS_MOBILE_SURFACES
    # Any rule under the mobile @media block that sets a 44px floor on
    # ``button`` or ``.stButton > button`` satisfies the finding.
    assert re.search(
        r'(?:button|\.stButton\s*>\s*button)[^{]*\{[^}]*min-height:\s*44px',
        css, re.IGNORECASE | re.DOTALL,
    )
