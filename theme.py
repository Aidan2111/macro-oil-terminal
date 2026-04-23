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

_CSS_CHECKLIST = """
.checklist {
  list-style: none; padding: 0; margin: 12px 0 0 0;
  display: flex; flex-direction: column; gap: 10px;
}
.checklist-item {
  display: flex; align-items: center; gap: 10px;
  font-size: 14px;
  color: var(--text-primary);
}
.checklist-item[data-checked="true"] {
  color: var(--text-secondary); /* muted when checked, so unchecked rows pop */
}
.checklist-item svg { flex-shrink: 0; }
"""

_CSS_COUNTDOWN = """
.catalyst-countdown {
  display: inline-block;
  font-size: 13px;
  font-weight: 500;
  padding: 4px 10px;
  border-radius: 6px;
  background: rgba(34, 211, 238, 0.08);
  letter-spacing: 0.2px;
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
    _CSS_CHECKLIST,
    _CSS_COUNTDOWN,
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


# ---------------------------------------------------------------------------
# T2 — hero render helpers: stance pill, conviction bar, tier card.
#
# Each helper emits HTML via ``st.markdown(..., unsafe_allow_html=True)``
# and styles against the CSS classes declared in ``_CSS_*`` above. Outside
# a Streamlit runtime they return silently (mirrors ``inject_css``) so the
# module stays safe to import from tests and scripts.
# ---------------------------------------------------------------------------
def _stance_color(stance: str) -> str:
    """Map a stance enum to a PALETTE token used for glow / accent / fill.

    ``LONG_SPREAD`` and ``SHORT_SPREAD`` get the directional semantic
    colors; everything else (``FLAT``, ``STAND_ASIDE``, or unknown) falls
    back to the active-brand ``primary`` so neutral stances still
    register visually without screaming at the reader.
    """
    s = (stance or "").upper()
    if s == "LONG_SPREAD":
        return PALETTE.positive
    if s == "SHORT_SPREAD":
        return PALETTE.negative
    return PALETTE.primary


def _has_streamlit_runtime() -> bool:
    """Return True only if ``st.markdown`` is a live callable.

    Used to early-exit the render helpers when imported from a script or
    test without a Streamlit runtime — the module-level ``import
    streamlit as st`` always succeeds, but calling ``st.markdown``
    outside a runtime is a no-op at best, a warning spam at worst.
    """
    return hasattr(st, "markdown") and callable(getattr(st, "markdown", None))


def render_stance_pill(stance: str) -> None:
    """Render the hero stance pill (UIP-T2).

    Display label pulls from ``language.TERMS`` so the plain-English
    rename stays single-source. Color for the glow/text lives in
    ``PALETTE``: positive for LONG_SPREAD, negative for SHORT_SPREAD,
    text_secondary for FLAT / STAND_ASIDE / unknown.
    """
    if not _has_streamlit_runtime():
        return

    from language import TERMS

    s = (stance or "").upper()
    if s == "LONG_SPREAD":
        color = PALETTE.positive
        display = TERMS["long_spread"].upper()
    elif s == "SHORT_SPREAD":
        color = PALETTE.negative
        display = TERMS["short_spread"].upper()
    else:
        color = PALETTE.text_secondary
        display = TERMS["flat"].upper()

    st.markdown(
        f'<div class="stance-pill" data-testid="stance-pill" '
        f'style="color:{color}; box-shadow: 0 0 20px {color}55;">{display}</div>',
        unsafe_allow_html=True,
    )


def render_conviction_bar(value: int, stance: str) -> None:
    """Render the hero conviction bar (UIP-T2).

    ``value`` is a 1-10 conviction integer — clamped to ``[0, 10]`` so
    upstream bugs can't push the fill past 100%. Bar color tracks the
    stance's directional semantic (positive / negative) or primary for
    neutral stances; the caption uses ``language.describe_confidence``
    to render the qualitative band label.
    """
    if not _has_streamlit_runtime():
        return

    from language import describe_confidence

    try:
        v = int(value)
    except (TypeError, ValueError):
        v = 0
    v = max(0, min(10, v))
    pct = v * 10
    color = _stance_color(stance)
    label = f"Confidence: {describe_confidence(v)} ({v}/10)"

    st.markdown(
        f'<div class="caption" style="color: var(--text-secondary); '
        f'margin-bottom: 4px;">{label}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="conviction-bar" role="progressbar" '
        f'aria-valuenow="{v}" aria-valuemin="0" aria-valuemax="10" '
        f'data-testid="conviction-bar" data-conviction="{v}">'
        f'<div class="conviction-bar-fill" '
        f'style="width: {pct}%; background: {color};"></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_tier_card(instrument, tier_key: str, stance: str) -> None:
    """Render a single execution-tier card (UIP-T2).

    ``instrument`` is a ``trade_thesis.Instrument`` (or any object with
    ``.tier``, ``.name``, plus optional ``.legs`` / ``.size_usd`` /
    ``.symbol`` fields). ``tier_key`` is the ``data-tier`` attribute
    value — pass ``"tier1"`` / ``"tier2"`` / ``"tier3"`` so sentinel
    tests can target each card directly. The P&L preview is a stub —
    P1.2 replaces it with a real broker-side number.
    """
    if not _has_streamlit_runtime():
        return

    # Legs string: prefer ``.legs`` (list or str). Fall back to ``.symbol``
    # so the card still renders for Instruments minted before the ``legs``
    # field existed.
    legs = getattr(instrument, "legs", None)
    if isinstance(legs, (list, tuple)):
        legs_str = " / ".join(str(x) for x in legs)
    elif isinstance(legs, str):
        legs_str = legs
    else:
        legs_str = str(getattr(instrument, "symbol", "") or "")

    # P&L preview — deliberately a stub. Tier 1 has no sizing at all;
    # Tiers 2/3 display a 1% nominal move against ``size_usd`` when the
    # caller has attached one, or a TBD placeholder otherwise.
    tier = int(getattr(instrument, "tier", 0) or 0)
    size_usd = getattr(instrument, "size_usd", None)
    if tier == 1:
        pl_preview = "P&L @ 1σ: —"
    elif size_usd is not None:
        try:
            pl_preview = "P&L @ 1σ: $" + format(abs(float(size_usd)) * 0.01, ",.0f")
        except (TypeError, ValueError):
            pl_preview = "P&L @ 1σ: TBD"
    else:
        pl_preview = "P&L @ 1σ: TBD"

    accent = _stance_color(stance)
    name = str(getattr(instrument, "name", "") or "")

    st.markdown(
        f'<div class="tier-card" data-testid="tier-card" data-tier="{tier_key}">'
        f'<div class="tier-card-accent" style="background:{accent}"></div>'
        f'<div class="tier-card-header">{name}</div>'
        f'<div class="tier-card-legs">{legs_str}</div>'
        f'<div class="tier-card-pl">{pl_preview}</div>'
        f'<div class="tier-card-footer">[execute — wiring]</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# T3 — styled checklist + EIA catalyst countdown.
#
# Lucide SVGs are inlined (no CDN) so the helpers render with zero network
# dependency and the stroke color can be data-bound to a PALETTE token.
# The check-circle mark uses a path + polyline; the empty circle uses a
# single <circle> element — the two signatures are distinct enough that
# the unit tests can assert each independently.
# ---------------------------------------------------------------------------
_LUCIDE_CHECK_CIRCLE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" '
    'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>'
    '<polyline points="22 4 12 14.01 9 11.01"/></svg>'
)

_LUCIDE_CIRCLE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" '
    'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2">'
    '<circle cx="12" cy="12" r="10"/></svg>'
)


def render_checklist(items) -> None:
    """Render the pre-trade checklist as a styled ``<ul>`` (UIP-T3).

    ``items`` is a list of ``trade_thesis.ChecklistItem`` (or any object
    exposing ``.prompt`` + ``.auto_check``). An item is considered
    "satisfied" when ``auto_check is True``; ``False`` and ``None`` both
    render as unchecked — ``None`` means the user must tick it manually,
    and the interactive ``st.checkbox`` toggles live in an expander
    alongside the styled list (see ``app._render_checklist``).

    The list carries ``data-testid="checklist"`` so Playwright can target
    it; each row carries ``data-checked="true"|"false"`` for CSS tinting
    and sentinel assertions. Outside a Streamlit runtime the helper
    returns silently (mirrors ``inject_css`` / the T2 helpers).
    """
    if not _has_streamlit_runtime():
        return

    if not items:
        # Emit the empty wrapper so the data-testid still resolves.
        st.markdown(
            '<ul class="checklist" data-testid="checklist"></ul>',
            unsafe_allow_html=True,
        )
        return

    rows: list[str] = []
    for item in items:
        auto = getattr(item, "auto_check", None)
        checked = auto is True
        if checked:
            svg = _LUCIDE_CHECK_CIRCLE.format(color=PALETTE.positive)
        else:
            svg = _LUCIDE_CIRCLE.format(color=PALETTE.text_secondary)
        label = str(getattr(item, "prompt", "") or "")
        rows.append(
            f'<li class="checklist-item" data-checked="{str(checked).lower()}">'
            f'{svg}<span>{label}</span></li>'
        )

    st.markdown(
        '<ul class="checklist" data-testid="checklist">' + "".join(rows) + "</ul>",
        unsafe_allow_html=True,
    )


def render_catalyst_countdown(hours_to_eia) -> None:
    """Render the EIA catalyst countdown pill (UIP-T3).

    ``hours_to_eia`` is a float from ``ThesisContext.hours_to_next_eia``.
    ``None`` or a negative value both render the neutral
    ``"⏱ No scheduled catalyst"`` sentinel in ``text_secondary``; a
    non-negative float renders ``"⏱ EIA release in Xd Yh"`` in the
    ``primary`` token.

    Hour remainder uses Python's built-in ``round()`` — banker's
    rounding — so 14.5 → 14, not 15. This choice is locked in by the
    unit tests; T5 chart tick labels should match so the UI stays
    numerically consistent across surfaces. ``0.4`` → ``"0d 0h"``,
    ``5.0`` → ``"0d 5h"``, ``48.0`` → ``"2d 0h"``.
    """
    if not _has_streamlit_runtime():
        return

    if hours_to_eia is None or hours_to_eia < 0:
        st.markdown(
            f'<div class="catalyst-countdown" data-testid="catalyst-countdown" '
            f'style="color: {PALETTE.text_secondary};">'
            f'\u23f1 No scheduled catalyst</div>',
            unsafe_allow_html=True,
        )
        return

    try:
        hrs = float(hours_to_eia)
    except (TypeError, ValueError):
        st.markdown(
            f'<div class="catalyst-countdown" data-testid="catalyst-countdown" '
            f'style="color: {PALETTE.text_secondary};">'
            f'\u23f1 No scheduled catalyst</div>',
            unsafe_allow_html=True,
        )
        return

    d = int(hrs // 24)
    h = int(round(hrs % 24))
    # Wrap-over: round() can push 23.5h → 24, which should then roll a day.
    if h == 24:
        d += 1
        h = 0

    st.markdown(
        f'<div class="catalyst-countdown" data-testid="catalyst-countdown" '
        f'style="color: {PALETTE.primary};">'
        f'\u23f1 EIA release in {d}d {h}h</div>',
        unsafe_allow_html=True,
    )
