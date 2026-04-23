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
from streamlit.components.v1 import html as _components_html


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
.ticker-symbol {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.ticker-price {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}
.ticker-delta {
  font-size: 12px;
  font-weight: 500;
}
.ticker-sparkline {
  height: 24px;
  width: 80px;
  display: inline-block;
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

# UIP-T6 — surface-specific mobile overrides. Kept in a second named
# chunk so the T1 mobile block stays intact (a unit test asserts the
# original ``[data-testid="column"] { flex-direction: column; }`` rule
# survives) and so reviewers can see the T6 additions in one place.
#
# The ``!important`` markers are load-bearing in three spots:
#   * ``.block-container`` padding — Streamlit's theme override wins
#     without it, so the page never actually narrows to the 0.75rem pad.
#   * ``[data-testid="column"]`` flex rules — Streamlit ships a flex-row
#     default inline that needs the cascade bump to flip to column
#     stacking.
#   * ``.js-plotly-plot .main-svg`` width — Plotly pins the SVG width in
#     JS, so CSS has to raise its hand with ``!important`` to keep the
#     chart inside the viewport after the tab-switch rerender.
_CSS_MOBILE_SURFACES = """
@media (max-width: 768px) {
  /* Tighter page padding — overrides Streamlit's default. */
  .block-container { padding: 0.75rem 0.75rem !important; }

  /* Ticker strip: already wraps from T1; narrow items so more fit. */
  .ticker-item { min-width: 140px; font-size: 13px; }
  .ticker-sparkline { width: 60px; }

  /* Hero surfaces — stance pill flexes, countdown full-width. */
  .stance-pill { min-width: 0; width: auto; padding: 6px 12px; font-size: 13px; }
  .conviction-bar, .conviction-bar-fill { height: 10px; }
  .catalyst-countdown { width: 100%; text-align: center; box-sizing: border-box; }

  /* Tier tiles stack with breathing room between them. */
  .tier-card { width: 100%; margin-bottom: 12px; }

  /* Checklist: tighter padding + smaller rows. */
  .checklist { padding-left: 4px; }
  .checklist-item { font-size: 13px; gap: 8px; }

  /* Charts: force Plotly SVG to recompute to the column width. */
  .js-plotly-plot .main-svg { width: 100% !important; }
  .js-plotly-plot, .stPlotlyChart { max-width: 100% !important; }

  /* Streamlit column flex — force stacking on narrow viewports.
     Without this the three tier-card columns sit side-by-side on
     phones and horizontally overflow the 375px viewport. */
  [data-testid="column"] {
    flex: 1 1 100% !important;
    width: 100% !important;
    min-width: 0 !important;
  }
  [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }

  /* Footer: trim padding, shrink copy. */
  .app-footer { padding: 16px 8px; font-size: 11px; }

  /* Empty / error cards: keep inside the viewport without the
     default 16px vertical margins stacking up visually. */
  .empty-state, .error-state { margin: 12px 0; padding: 18px 12px; }
}
"""

# UIP-T7 — empty + error state cards. Both share the centered layout
# + padding + border-radius; the error variant overrides the background
# and border tint to the alert color at 6% / 30% opacity.
_CSS_STATES = """
.empty-state, .error-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 24px 16px;
  background: var(--bg-2);
  border: 1px solid var(--border);
  border-radius: 12px;
  gap: 8px;
  margin: 16px 0;
}
.empty-state-icon, .error-state-icon {
  opacity: 0.7;
}
.empty-state-icon svg, .error-state-icon svg {
  width: 32px; height: 32px;
}
.empty-state-message { color: var(--text-secondary); font-size: 14px; }
.error-state {
  background: rgba(239, 68, 68, 0.06);
  border-color: rgba(239, 68, 68, 0.3);
}
.error-state-message { color: var(--alert); font-size: 14px; font-weight: 500; }
"""

_CSS_FOOTER = """
.app-footer {
  text-align: center;
  color: var(--text-muted);
  font-size: 12px;
  padding: 24px 16px;
  margin-top: 48px;
  border-top: 1px solid var(--border);
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
    _CSS_STATES,
    _CSS_FOOTER,
    _CSS_MOBILE,
    _CSS_MOBILE_SURFACES,
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


# ---------------------------------------------------------------------------
# T4 — Bloomberg-tape ticker strip.
#
# The strip renders at the very top of ``app.py`` (above the hero band) and
# carries one ``.ticker-item`` per quote. Each item shows symbol, price,
# delta (abs + pct, always signed), and a tiny 80x24 inline-SVG sparkline
# — no Plotly, no network, no external CSS. Keeping the SVG hand-rolled
# means per-render cost is sub-millisecond and the strip can live inside
# an ``st.fragment(run_every=...)`` without a Plotly re-mount on every
# tick.
# ---------------------------------------------------------------------------
SYMBOL_DISPLAY_NAMES = {
    "BZ=F": "Brent",
    "CL=F": "WTI",
    "HO=F": "Heating Oil",
    "RB=F": "RBOB",
    "USO": "USO ETF",
    "BNO": "BNO ETF",
}


def _build_sparkline_polyline(
    values, width: int = 80, height: int = 24, margin: int = 2
) -> str:
    """Return the ``points`` attribute for an 80x24 sparkline polyline.

    ``values`` is min-max scaled into ``y ∈ [height - margin, margin]``
    (SVG y grows downward, so larger values sit higher). When every
    value is identical, the line is flat at the vertical midpoint. The
    caller is responsible for skipping the surrounding ``<svg>`` when
    ``values`` is empty / None — this helper assumes at least one value.
    """
    try:
        xs = [float(v) for v in values]
    except (TypeError, ValueError):
        return ""
    n = len(xs)
    if n == 0:
        return ""
    if n == 1:
        # One point — render a flat tick at the midpoint.
        mid = height / 2
        return f"0,{mid:.2f} {width:.2f},{mid:.2f}"

    lo, hi = min(xs), max(xs)
    span = hi - lo
    y_top = float(margin)
    y_bot = float(height - margin)
    step = width / (n - 1)
    pts: list[str] = []
    for i, v in enumerate(xs):
        x = i * step
        if span == 0:
            y = height / 2
        else:
            # Invert: highest value → smallest y (top).
            y = y_bot - (v - lo) / span * (y_bot - y_top)
        pts.append(f"{x:.2f},{y:.2f}")
    return " ".join(pts)


def _safe_float(value, default: float = 0.0) -> float:
    """Coerce to float; fall back to ``default`` on None / garbage."""
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _ticker_item_html(q: dict) -> str:
    """Return the HTML string for a single ``.ticker-item`` block."""
    symbol = str(q.get("symbol", "") or "")
    label = str(q.get("display_name") or symbol)
    price = _safe_float(q.get("price"))
    d_abs = _safe_float(q.get("delta_abs"))
    d_pct = _safe_float(q.get("delta_pct"))

    if d_pct > 0:
        color = PALETTE.positive
    elif d_pct < 0:
        color = PALETTE.negative
    else:
        color = PALETTE.text_secondary

    spark_values = q.get("sparkline_values") or []
    if spark_values:
        points = _build_sparkline_polyline(spark_values)
        svg = (
            '<svg viewBox="0 0 80 24" class="ticker-sparkline" '
            'xmlns="http://www.w3.org/2000/svg">'
            f'<polyline points="{points}" fill="none" '
            f'stroke="{color}" stroke-width="1.5" '
            f'stroke-linejoin="round" /></svg>'
        )
    else:
        svg = ""

    return (
        f'<div class="ticker-item" data-symbol="{symbol}">'
        f'<span class="ticker-symbol">{label}</span>'
        f'<span class="ticker-price mono">${price:,.2f}</span>'
        f'<span class="ticker-delta" style="color: {color};">'
        f'{d_abs:+.2f} ({d_pct:+.2f}%)</span>'
        f'{svg}</div>'
    )


# ---------------------------------------------------------------------------
# T5 — apply_theme(fig) + chart polish helpers.
#
# ``apply_theme(fig)`` is the single entry point every Plotly call site in
# ``app.py`` routes through. It mutates the figure's layout in place and
# returns the same figure so callers can one-line it:
#
#     st.plotly_chart(apply_theme(fig), ...)
#
# Plotly is imported lazily inside the function so importing ``theme`` in a
# stripped-down environment (e.g. a script that only needs ``inject_css``)
# does not pull in plotly. The type hint is stringified for the same reason.
#
# ``pretty_axis_label`` + ``format_money_hover`` are small string helpers
# shared by the app.py chart-polish sweep — kept pure so they unit-test
# cleanly without any figure fixture.
# ---------------------------------------------------------------------------
_FONT_FAMILY = "Source Sans Pro, -apple-system, sans-serif"


def apply_theme(fig):
    """Apply the brand palette to a Plotly figure (UIP-T5).

    Mutates ``fig.layout`` in place *and* returns the same figure, so
    callers can inline the call: ``st.plotly_chart(apply_theme(fig))``.

    What gets set:
    * ``paper_bgcolor`` / ``plot_bgcolor`` — ``PALETTE.bg_1`` so charts
      blend with the page chrome.
    * ``font`` — primary-text color, Source Sans Pro stack.
    * ``xaxis`` / ``yaxis`` — faint gridlines + zerolines, border-tinted
      axis lines, secondary-text tick labels.
    * ``hoverlabel`` — dark ``bg_2`` box, bordered in ``PALETTE.border``,
      primary-text contents. Per-trace ``hovertemplate`` strings are
      left intact — Plotly merges them with the layout default.
    * ``margin`` — ``l=40, r=20, t=40, b=30`` per design spec.
    * ``colorway`` — cyan-primary first so the first trace inherits the
      brand colour without needing per-trace overrides.
    * ``legend`` — bg_2 box + border + primary-text.
    * ``title.font`` — only touched when a title already exists, so
      untitled figures don't grow a phantom title frame.
    """
    update = dict(
        paper_bgcolor=PALETTE.bg_1,
        plot_bgcolor=PALETTE.bg_1,
        font=dict(color=PALETTE.text_primary, family=_FONT_FAMILY),
        xaxis=dict(
            gridcolor=PALETTE.gridline,
            zerolinecolor=PALETTE.gridline,
            linecolor=PALETTE.border,
            tickfont=dict(color=PALETTE.text_secondary),
        ),
        yaxis=dict(
            gridcolor=PALETTE.gridline,
            zerolinecolor=PALETTE.gridline,
            linecolor=PALETTE.border,
            tickfont=dict(color=PALETTE.text_secondary),
        ),
        hoverlabel=dict(
            bgcolor=PALETTE.bg_2,
            bordercolor=PALETTE.border,
            font=dict(color=PALETTE.text_primary, family=_FONT_FAMILY),
        ),
        margin=dict(l=40, r=20, t=40, b=30),
        colorway=[
            PALETTE.primary,
            PALETTE.warn,
            PALETTE.positive,
            PALETTE.alert,
            PALETTE.text_secondary,
        ],
        legend=dict(
            bgcolor=PALETTE.bg_2,
            bordercolor=PALETTE.border,
            font=dict(color=PALETTE.text_primary),
        ),
    )

    # Only restyle the title when one already exists — otherwise Plotly
    # reserves vertical space for an empty title frame and the chart
    # shifts down visibly.
    try:
        existing_title = getattr(fig.layout.title, "text", None)
    except Exception:
        existing_title = None
    if existing_title:
        update["title"] = dict(
            text=existing_title,
            font=dict(color=PALETTE.text_primary, size=18),
        )

    fig.update_layout(**update)
    return fig


# ---------------------------------------------------------------------------
# Axis-label + hover helpers.
#
# ``pretty_axis_label`` translates snake-case keys to plain-English via
# ``language.TERMS``, with a small table of extra synonyms (``z_score`` →
# stretch) + suffix rules so the call sites don't have to hand-maintain a
# second mapping. Unknown keys fall through to title-case — safe for any
# random identifier a chart might hand in.
# ---------------------------------------------------------------------------
_AXIS_LABEL_ALIASES = {
    # Common quant-side aliases that don't appear verbatim in TERMS.
    "z_score": "stretch",
    "zscore": "stretch",
    "dislocation": "stretch",
    "conviction": "confidence",
}

_AXIS_SUFFIX_RULES = (
    ("_usd", " ($)"),
    ("_pct", " (%)"),
    ("_mbbl", " (Mbbl)"),
    ("_bbls", " (bbls)"),
    ("_bbl", " (bbl)"),
)


def pretty_axis_label(raw: str) -> str:
    """Translate a snake_case axis label to plain-English.

    Resolution order:
    1. If ``raw`` is a known alias, map it to the canonical ``TERMS`` key
       (``"z_score"`` → ``"stretch"`` → ``"Spread Stretch"``).
    2. If the alias-resolved key exists in ``language.TERMS``, return
       that display string.
    3. Otherwise strip a known suffix (``_usd`` → ``" ($)"`` etc.), then
       title-case what's left and reattach the suffix. So ``"spread_usd"``
       → ``"Spread ($)"``, ``"inventory_mbbl"`` → ``"Inventory (Mbbl)"``.
    4. If no suffix matched, plain ``title()`` on the snake-case string
       (underscores → spaces). ``"unknown_field"`` → ``"Unknown Field"``.

    Unknown / empty inputs coerce to ``str`` and fall through to step 4
    — never raises. T5 is about applying the theme, not exhaustively
    renaming every axis; extend this table as new call sites surface.
    """
    from language import TERMS  # local import — avoid module cycle risk.

    key = str(raw or "").strip().lower()
    if not key:
        return ""

    # Step 1 — alias collapse.
    resolved = _AXIS_LABEL_ALIASES.get(key, key)
    # Step 2 — TERMS lookup.
    if resolved in TERMS:
        return TERMS[resolved]

    # Step 3 — strip a known suffix, title-case the stem, reattach.
    for suffix, pretty_suffix in _AXIS_SUFFIX_RULES:
        if key.endswith(suffix):
            stem = key[: -len(suffix)]
            stem_pretty = stem.replace("_", " ").title() if stem else ""
            return f"{stem_pretty}{pretty_suffix}".strip()

    # Step 4 — plain title-case fallback.
    return key.replace("_", " ").title()


def format_money_hover(value: float) -> str:
    """Format a numeric value as ``$X,XXX.XX`` for hover templates.

    Uses Python's locale-independent ``:,`` thousands separator with two
    decimal places. Raises the usual ``TypeError`` / ``ValueError`` if
    the caller hands in something that can't be coerced to ``float`` —
    hover-template callers are expected to feed already-numeric values.
    """
    return f"${float(value):,.2f}"


def render_ticker_strip(quotes) -> None:
    """Render the Bloomberg-tape ticker strip (UIP-T4).

    ``quotes`` is a list of dicts; each dict must carry ``symbol``,
    ``price``, ``delta_abs``, ``delta_pct``, and ``sparkline_values``.
    An optional ``display_name`` overrides ``symbol`` in the label. The
    helper emits a single ``st.markdown(..., unsafe_allow_html=True)``
    with one ``<div class="ticker-item">`` per quote. Outside a
    Streamlit runtime it returns silently (matches the T2/T3 helpers).
    """
    if not _has_streamlit_runtime():
        return
    inner = "".join(_ticker_item_html(q) for q in (quotes or []))
    st.markdown(
        '<div class="ticker-strip" data-testid="ticker-strip">'
        + inner
        + '</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# T7 — loading + empty + error state primitives.
#
# Three helpers that harden the app against network / data failures and
# give blank-data branches a centered illustrated state instead of a
# silent empty chart. All three are no-ops outside a Streamlit runtime
# so the module stays safe to import from tests and scripts.
#
# Icons are inlined Lucide SVGs (no CDN, no network dependency) so the
# per-render cost stays sub-millisecond and the stroke color can be
# data-bound to a PALETTE token.
# ---------------------------------------------------------------------------
_LUCIDE_INBOX = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round">'
    '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/>'
    '<path d="M5.45 5.11L2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>'
    '</svg>'
)

_LUCIDE_TRENDING_UP = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round">'
    '<polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/>'
    '<polyline points="17 6 23 6 23 12"/>'
    '</svg>'
)

_LUCIDE_SEARCH = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="11" cy="11" r="8"/>'
    '<line x1="21" y1="21" x2="16.65" y2="16.65"/>'
    '</svg>'
)

_LUCIDE_ALERT_CIRCLE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round">'
    '<circle cx="12" cy="12" r="10"/>'
    '<line x1="12" y1="8" x2="12" y2="12"/>'
    '<line x1="12" y1="16" x2="12.01" y2="16"/>'
    '</svg>'
)

_LUCIDE_ALERT_TRIANGLE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'fill="none" stroke="currentColor" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>'
    '<line x1="12" y1="9" x2="12" y2="13"/>'
    '<line x1="12" y1="17" x2="12.01" y2="17"/>'
    '</svg>'
)

_EMPTY_ICONS = {
    "inbox": _LUCIDE_INBOX,
    "trending-up": _LUCIDE_TRENDING_UP,
    "search": _LUCIDE_SEARCH,
    "alert-circle": _LUCIDE_ALERT_CIRCLE,
}


class _NoopStatus:
    """Fallback context manager used when there's no Streamlit runtime.

    Mirrors the ``with st.status(...) as s:`` shape so callers can use
    ``render_loading_status(...)`` unconditionally from scripts / tests
    without wrapping each call site in a runtime check.
    """

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def render_loading_status(label: str, *, expanded: bool = False):
    """Return a context manager that wraps ``st.status(label, ...)`` (UIP-T7).

    Usage::

        with render_loading_status("Fetching live prices…"):
            data = fetch_pricing()

    Outside a Streamlit runtime, returns a no-op context manager so the
    same code path is safe in tests / scripts. ``expanded`` defaults to
    ``False`` so the status starts collapsed; pass ``expanded=True`` for
    long-running fetches where the user wants to see progress detail.
    """
    status_fn = getattr(st, "status", None)
    if status_fn is None or not callable(status_fn):
        return _NoopStatus()
    try:
        return status_fn(label, expanded=expanded)
    except Exception:
        # Older Streamlit versions may not accept ``expanded=`` — fall
        # back to the no-op so the calling ``with`` block is safe.
        return _NoopStatus()


def render_empty(icon: str, message: str) -> None:
    """Render a centered empty-state card (UIP-T7).

    ``icon`` selects from a small named set (``inbox`` / ``trending-up``
    / ``search`` / ``alert-circle``); unknown values silently fall back
    to ``inbox`` so the card always renders. The card carries
    ``data-testid="empty-state"`` so Playwright can target it.
    """
    if not _has_streamlit_runtime():
        return
    svg = _EMPTY_ICONS.get(icon, _LUCIDE_INBOX)
    st.markdown(
        '<div class="empty-state" data-testid="empty-state">'
        f'<div class="empty-state-icon">{svg}</div>'
        f'<div class="empty-state-message">{message}</div>'
        '</div>',
        unsafe_allow_html=True,
    )


def render_error(message: str, retry_fn=None) -> None:
    """Render a styled error card with an optional retry button (UIP-T7).

    The card carries ``data-testid="error-state"`` and an inline
    ``alert-triangle`` Lucide SVG. When ``retry_fn`` is not None, a
    native ``st.button("Retry now", ...)`` renders below the markdown
    block; clicking it invokes ``retry_fn()`` and calls ``st.rerun()``
    so the next render re-fetches.

    Outside a Streamlit runtime the helper returns silently.
    """
    if not _has_streamlit_runtime():
        return
    st.markdown(
        '<div class="error-state" data-testid="error-state">'
        f'<div class="error-state-icon">{_LUCIDE_ALERT_TRIANGLE}</div>'
        f'<div class="error-state-message">{message}</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    if retry_fn is None:
        return
    # Native Streamlit button — rendered OUTSIDE the markdown block so
    # click handling works. ``key`` is stable per unique message so the
    # same error card can render twice in a page without a key clash.
    try:
        clicked = st.button("Retry now", key=f"retry-btn-{hash(message)}")
    except Exception:
        clicked = False
    if clicked:
        try:
            retry_fn()
        except Exception:
            # Never let a retry handler raise into the page.
            pass
        try:
            st.rerun()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# T8 — first-visit onboarding toasts.
#
# Rendered once at app boot (right after ``inject_css()``). The component
# is a self-contained HTML+JS blob mounted via ``st.components.v1.html``
# so the JS runs in its own iframe — localStorage in the iframe is
# sandboxed *per-origin*, and for Streamlit-served components the origin
# matches the parent page, so the flag is shared with any future
# localStorage reads the parent wants to make.
#
# The three copy strings are fixed per the design spec — generic "Macro
# Oil Terminal" branding, no personalization. A unit test enforces that
# invariant so a future copy edit that slips an "Aidan" back in fails in
# CI.
#
# CSS variables from the parent page do NOT reliably inherit into the
# components iframe, so colors are hardcoded to the brand hex values.
# ---------------------------------------------------------------------------
_ONB_COPY_1 = (
    "Welcome to Macro Oil Terminal \u2014 a research desk for crude "
    "spread dislocations. Hover any metric for the math."
)
_ONB_COPY_2 = (
    "The hero card is the current trade idea. Confidence tells you "
    "how strong the signal is."
)
_ONB_COPY_3 = "Scroll or click the tabs for the data behind the signal."

_ONB_CSS = """
.onb-root {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 9999;
  max-width: 340px;
  font-family: -apple-system, 'Segoe UI', sans-serif;
  pointer-events: none;
}
.onb-toast {
  background: #121826;
  border: 1px solid #2A3245;
  border-left: 3px solid #22D3EE;
  border-radius: 12px;
  padding: 14px 16px;
  margin-top: 8px;
  color: #E6EBF5;
  font-size: 13px;
  line-height: 1.5;
  box-shadow: 0 8px 24px rgba(0,0,0,0.3);
  opacity: 0;
  transform: translateY(4px);
  transition: opacity 0.2s ease, transform 0.2s ease;
  position: relative;
  pointer-events: auto;
}
.onb-toast.onb-toast-visible {
  opacity: 1;
  transform: translateY(0);
}
.onb-toast .onb-dismiss {
  position: absolute;
  top: 6px;
  right: 8px;
  background: transparent;
  border: none;
  color: #E6EBF5;
  opacity: 0.5;
  cursor: pointer;
  font-size: 13px;
  padding: 2px 6px;
  line-height: 1;
}
.onb-toast .onb-dismiss:hover {
  opacity: 1;
}
.onb-toast .onb-message {
  padding-right: 20px;
}
/* UIP-T6 — mobile: hug the bottom-right with tighter insets and cap the
   toast width against the viewport so it never clips. The 340px desktop
   max-width can overflow a 375px phone once the 24px gutters are in. */
@media (max-width: 768px) {
  .onb-root {
    right: 12px;
    bottom: 12px;
    max-width: calc(100vw - 24px);
  }
}
"""

# JS kept readable — string-escapes the three copy strings into a JSON
# array so the JS path is a single source-of-truth. The copy literals
# flow in via an f-string below.
_ONB_JS = """
(function () {
  var FLAG_KEY = "mot_onboarding_done";
  try {
    if (localStorage.getItem("mot_onboarding_done")) {
      return;
    }
  } catch (e) {
    return;
  }

  var MESSAGES = __ONB_MESSAGES__;
  var FADE_IN_MS = 200;
  var HOLD_MS = 8000;
  var FADE_OUT_MS = 400;

  var root = document.createElement("div");
  root.className = "onb-root";
  document.body.appendChild(root);

  var dismissed = false;
  var activeToasts = [];
  var timers = [];

  function clearTimers() {
    timers.forEach(function (t) { clearTimeout(t); });
    timers = [];
  }

  function fadeOut(toast) {
    toast.classList.remove("onb-toast-visible");
    var t = setTimeout(function () {
      if (toast && toast.parentNode) {
        toast.parentNode.removeChild(toast);
      }
    }, FADE_OUT_MS);
    timers.push(t);
  }

  function markDone() {
    try {
      localStorage.setItem("mot_onboarding_done", "1");
    } catch (e) { /* ignore */ }
  }

  function dismissAll() {
    if (dismissed) return;
    dismissed = true;
    clearTimers();
    activeToasts.forEach(fadeOut);
    activeToasts = [];
    markDone();
  }

  function spawnToast(message, onComplete) {
    var toast = document.createElement("div");
    toast.className = "onb-toast";
    // Sentinel attribute for Playwright — literal form: data-testid="onboarding-toast"
    toast.setAttribute("data-testid", "onboarding-toast");

    var msg = document.createElement("span");
    msg.className = "onb-message";
    msg.textContent = message;
    toast.appendChild(msg);

    var btn = document.createElement("button");
    btn.className = "onb-dismiss";
    btn.setAttribute("aria-label", "dismiss");
    btn.textContent = "\u2715";
    btn.addEventListener("click", function (ev) {
      ev.stopPropagation();
      dismissAll();
    });
    toast.appendChild(btn);

    root.appendChild(toast);
    activeToasts.push(toast);

    var tIn = setTimeout(function () {
      toast.classList.add("onb-toast-visible");
    }, 20);
    timers.push(tIn);

    var tOut = setTimeout(function () {
      if (dismissed) return;
      fadeOut(toast);
      var idx = activeToasts.indexOf(toast);
      if (idx >= 0) activeToasts.splice(idx, 1);
      if (onComplete) onComplete();
    }, FADE_IN_MS + HOLD_MS);
    timers.push(tOut);
  }

  function runSequence() {
    var i = 0;
    function next() {
      if (dismissed) return;
      if (i >= MESSAGES.length) {
        markDone();
        return;
      }
      var msg = MESSAGES[i];
      i += 1;
      spawnToast(msg, next);
    }
    next();
  }

  document.addEventListener("keydown", function (ev) {
    if (ev.key === "Escape" || ev.keyCode === 27) {
      dismissAll();
    }
  });
  document.addEventListener("click", function () {
    dismissAll();
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", runSequence);
  } else {
    runSequence();
  }
})();
"""


def _build_onboarding_html() -> str:
    """Assemble the onboarding HTML body.

    Kept as a function rather than a module-level constant so the three
    copy strings don't need to be escaped at import time and the unit
    tests can assert the final-rendered body rather than a template.
    """
    import json

    # ``ensure_ascii=False`` preserves the em-dash and other unicode
    # characters verbatim so the unit-test substring assertions match.
    messages_json = json.dumps(
        [_ONB_COPY_1, _ONB_COPY_2, _ONB_COPY_3],
        ensure_ascii=False,
    )
    js = _ONB_JS.replace("__ONB_MESSAGES__", messages_json)
    return (
        "<style>"
        + _ONB_CSS
        + "</style>"
        + "<script>"
        + js
        + "</script>"
    )


def render_onboarding() -> None:
    """Render the first-visit onboarding toast sequence (UIP-T8).

    Emits a tiny HTML+JS component at the current page position via
    ``st.components.v1.html`` (height=0 so it contributes no vertical
    space). The component guards on ``localStorage["mot_onboarding_done"]``
    and spawns three fixed toasts in sequence on first visit — ESC or a
    click anywhere dismisses the stack and sets the flag.

    Call once at app boot, right after ``inject_css()``. Outside a
    Streamlit runtime the helper returns silently (mirrors the other
    theme helpers) so tests / scripts can import this module freely.
    """
    if not _has_streamlit_runtime():
        return
    body = _build_onboarding_html()
    try:
        _components_html(body, height=0)
    except Exception:
        # Never let a components mount failure crash the page render.
        # The onboarding is a nice-to-have; the app must still boot.
        pass


# ---------------------------------------------------------------------------
# T9 — meta polish: build version resolver + footer.
#
# ``_resolve_build_version()`` reads ``BUILD_VERSION`` from the environment
# so CD can bake ``git rev-parse --short HEAD`` in at container build
# time. Local dev falls through to ``"dev"`` so the footer never surfaces
# a blank version.
#
# ``render_footer(version, region)`` writes a single centered line at
# the bottom of the page — the research-and-education disclaimer,
# resolved version, and deploy region. No personalization, no name — a
# unit test locks that invariant. The ``.app-footer`` CSS rule is
# declared alongside the other ``_CSS_*`` chunks above and composed into
# the single-injection ``_CSS`` blob.
# ---------------------------------------------------------------------------


def _resolve_build_version() -> str:
    """Return the deployed build version, or ``"dev"`` if unset.

    CD bakes ``BUILD_VERSION=<git sha>`` into the container env so the
    footer shows the actual deployed revision. Local dev / tests leave
    the env var unset and get the ``"dev"`` literal.
    """
    import os

    value = os.environ.get("BUILD_VERSION", "").strip()
    return value or "dev"


def render_footer(version: str | None = None, region: str = "canadaeast") -> None:
    """Render the app footer (UIP-T9).

    Emits a single centered line carrying the research-and-education
    disclaimer, the resolved build version, and the deploy region. The
    block carries ``data-testid="app-footer"`` so Playwright can target
    it. When ``version`` is ``None`` the resolver reads it from
    ``BUILD_VERSION`` (fallback ``"dev"``) so call sites can pass
    nothing and still get a well-formed footer.

    Copy is fixed — generic "Macro Oil Terminal" branding, zero
    personalization. A parametrised unit test enforces that invariant
    against a banned-strings set ({aidan, youbiquity, personal, ...}).
    Outside a Streamlit runtime the helper returns silently (mirrors
    the other theme helpers).
    """
    if not _has_streamlit_runtime():
        return
    resolved = version if version is not None else _resolve_build_version()
    # Render as "v<resolved>" — but skip the prefix if the caller already
    # passed a "v"-tagged string (e.g. ``v0.4.1``) so the footer doesn't
    # read ``vv0.4.1``. Git short-SHAs and ``"dev"`` get the ``v`` prefix
    # for visual consistency.
    display_version = resolved if resolved.startswith("v") else f"v{resolved}"
    st.markdown(
        f'<div class="app-footer" data-testid="app-footer">'
        f"Research &amp; education only \u00b7 {display_version} "
        f"\u00b7 deployed to {region}"
        f"</div>",
        unsafe_allow_html=True,
    )
