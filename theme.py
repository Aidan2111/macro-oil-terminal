"""Theme module — palette tokens + Streamlit CSS injection (UIP-T1).

This module exposes two things and nothing else:

* ``PALETTE`` — a frozen ``@dataclass`` with the 14 brand tokens from
  ``docs/brainstorms/ui-polish.md``. Future modules pull colors via
  ``from theme import PALETTE`` so the palette lives in one place.
* ``inject_css()`` — writes a single ``<style>`` block into the Streamlit
  page on first call; subsequent calls inside the same session are a
  no-op. Outside a Streamlit runtime it returns silently.

Component-level helpers (stance pill, conviction bar, tier card, Plotly
``apply_theme``, etc.) are explicitly out of scope for T1 — they land in
T2+ and compose on top of the CSS classes declared below.
"""

from __future__ import annotations

from dataclasses import dataclass

import streamlit as st


# ---------------------------------------------------------------------------
# Palette — exact values from docs/brainstorms/ui-polish.md. Frozen so no
# runtime code can shift a brand color by accident.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class _Palette:
    bg_1: str = "#0A0E1A"
    bg_2: str = "#121826"
    bg_3: str = "#1B2232"
    border: str = "#2A3245"
    text_primary: str = "#E6EBF5"
    text_secondary: str = "#9AA4B8"
    text_muted: str = "#5B6578"
    primary: str = "#22D3EE"
    primary_glow: str = "rgba(34, 211, 238, 0.35)"
    warn: str = "#F59E0B"
    alert: str = "#EF4444"
    positive: str = "#84CC16"
    negative: str = "#F43F5E"
    gridline: str = "rgba(255,255,255,0.06)"


PALETTE = _Palette()


# ---------------------------------------------------------------------------
# CSS — grouped by component so a reviewer can skim. Kept in named chunks
# so T2+ can reference / extend each section without hunting in a wall of
# text. The final blob is assembled once at import time.
# ---------------------------------------------------------------------------
_CSS_ROOT_VARS = f"""
:root {{
  --bg-1: {PALETTE.bg_1};
  --bg-2: {PALETTE.bg_2};
  --bg-3: {PALETTE.bg_3};
  --border: {PALETTE.border};
  --text-primary: {PALETTE.text_primary};
  --text-secondary: {PALETTE.text_secondary};
  --text-muted: {PALETTE.text_muted};
  --primary: {PALETTE.primary};
  --primary-glow: {PALETTE.primary_glow};
  --warn: {PALETTE.warn};
  --alert: {PALETTE.alert};
  --positive: {PALETTE.positive};
  --negative: {PALETTE.negative};
  --gridline: {PALETTE.gridline};
}}
"""

_CSS_TYPOGRAPHY = """
h1 { font-size: 36px; font-weight: 700; }
h2 { font-size: 24px; font-weight: 600; }
h3 { font-size: 18px; font-weight: 600; }
body, .stMarkdown p { font-size: 14px; font-weight: 400; }
.caption, .stCaption, small { font-size: 12px; font-weight: 400; color: var(--text-muted); }
.mono { font-family: 'JetBrains Mono', ui-monospace, SFMono-Regular, monospace; }
"""

_CSS_SPACING = """
.block-container { padding-top: 1rem !important; }
.stMarkdown + .stMarkdown { margin-top: 24px; }
"""

_CSS_TABS = """
[data-baseweb="tab-list"] [aria-selected="true"] {
  color: var(--primary);
  border-bottom: 2px solid var(--primary);
}
"""

_CSS_BUTTONS = """
.stButton > button[data-baseweb="button"][kind="primary"]:hover {
  box-shadow: 0 0 20px var(--primary-glow);
}
"""

_CSS_STANCE_PILL = """
.stance-pill {
  display: inline-block;
  padding: 6px 14px;
  border-radius: 999px;
  font-size: 14px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  min-width: 160px;
  text-align: center;
}
"""

_CSS_CONVICTION_BAR = """
.conviction-bar {
  height: 8px;
  border-radius: 4px;
  background: var(--bg-3);
  overflow: hidden;
}
.conviction-bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.3s ease;
}
"""

_CSS_TIER_CARD = """
.tier-card {
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  position: relative;
  overflow: hidden;
}
.tier-card-accent {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 4px;
}
"""

_CSS_TICKER_STRIP = """
.ticker-strip {
  background: var(--bg-2);
  height: 40px;
  display: flex;
  align-items: center;
  overflow-x: auto;
  gap: 24px;
  padding: 0 16px;
  white-space: nowrap;
  scrollbar-width: thin;
}
.ticker-item {
  min-width: 160px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
"""

_CSS_MOBILE = """
@media (max-width: 768px) {
  .block-container { padding: 0.5rem !important; }
  .stance-pill { min-width: unset; width: 100%; }
  .tier-card { width: 100%; }
  .ticker-strip { height: auto; flex-wrap: wrap; }
  [data-testid="column"] { flex-direction: column; }
}
"""

_CSS = "<style>" + "".join([
    _CSS_ROOT_VARS,
    _CSS_TYPOGRAPHY,
    _CSS_SPACING,
    _CSS_TABS,
    _CSS_BUTTONS,
    _CSS_STANCE_PILL,
    _CSS_CONVICTION_BAR,
    _CSS_TIER_CARD,
    _CSS_TICKER_STRIP,
    _CSS_MOBILE,
]) + "</style>"


_INJECTED_FLAG = "_theme_css_injected"


def inject_css() -> None:
    """Inject the theme ``<style>`` block once per Streamlit session.

    Idempotent: the first call writes the blob and sets a session flag;
    subsequent calls short-circuit. Outside a Streamlit runtime (no
    ``st.session_state``) the function returns silently so module import
    in tests / scripts doesn't blow up.
    """
    try:
        state = st.session_state
    except Exception:
        # No Streamlit runtime (e.g. import-time tooling). Nothing to do.
        return

    try:
        if state.get(_INJECTED_FLAG):
            return
    except Exception:
        # session_state might be a stub without .get; fall through and
        # attempt the subscript path below.
        if _INJECTED_FLAG in state and state[_INJECTED_FLAG]:
            return

    st.markdown(_CSS, unsafe_allow_html=True)
    state[_INJECTED_FLAG] = True
