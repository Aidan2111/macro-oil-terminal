# UI polish pass — Design spec

> **Status:** APPROVED (2026-04-22 00:58Z). Review target: 5 minutes.
> Skim the module surface + the CSS contract + the Playwright sentinels,
> and you know how the 10 TDD tasks hang together.

## One-paragraph summary

A new `theme.py` module owns the palette, typography, and a single CSS
injection. Every Plotly chart routes through `theme.apply_theme(fig)`.
Hero band helpers get restyled (stance pill + conviction bar + tier
cards + checklist + catalyst countdown). A new ticker-strip component
replaces the sparkline tiles with a Bloomberg-style horizontal tape.
Global loading / empty / error primitives live in `theme.py`. A
first-visit 3-step toast sequence uses a tiny HTML component. Logo +
favicon + page title + footer land in a meta-polish task. All changes
gated by Playwright visual tests (screenshot diffs) + one desktop and
one mobile viewport. No layout refactor (tabs-vs-single-scroll deferred
to P2).

## Module surface

New files:

```
theme.py                      # PALETTE, inject_css(), apply_theme(fig),
                              #   render_empty(), render_error(),
                              #   render_loading_status(),
                              #   render_ticker_strip(quotes),
                              #   render_conviction_bar(value, stance),
                              #   render_stance_pill(stance),
                              #   render_catalyst_countdown(hours_to_eia)
static/logo.svg               # oil-barrel + dislocation arrow, 64x64
static/favicon.ico            # derived from logo
tests/e2e/screenshots/        # golden screenshots (checked in)
  hero_desktop.png
  hero_mobile.png
  macro_tab.png
  depletion_tab.png
  fleet_tab.png
```

Modified:

```
.streamlit/config.toml        # base palette + font
app.py                        # one-line theme.inject_css() at top
                              #   → then all chart calls go via apply_theme
                              #   → hero helpers delegate to theme.render_*
                              #   → ticker moves above hero
data_ingestion.py             # wrap public fns in try/except that
                              #   returns a typed error, never raises
providers/*.py                # same pattern
```

## `.streamlit/config.toml`

```toml
[theme]
base = "dark"
primaryColor = "#22D3EE"
backgroundColor = "#0A0E1A"
secondaryBackgroundColor = "#121826"
textColor = "#E6EBF5"
font = "sans serif"
```

## `theme.PALETTE`

Frozen dataclass, fields exactly as in the brainstorm's palette table.
Import from anywhere via `from theme import PALETTE`.

## `theme.inject_css()`

Idempotent, guarded by `st.session_state["_theme_css_injected"]`. The
CSS covers:

- Typography hierarchy (h1/h2/h3/body/caption/mono sizes).
- Spacing — `.block-container { padding-top: 1rem !important; }` plus
  `.stMarkdown + .stMarkdown { margin-top: 24px; }` for breathing room.
- Tab strip — active tab underline + primary-color text.
- Button primary — primary + primary_glow box-shadow on hover.
- Stance pill — class `stance-pill`, padding 6px 14px, border-radius
  999px, font 14/600 uppercase letter-spacing 0.5px, box-shadow
  `0 0 20px var(--primary-glow)`, `min-width: 160px` so it doesn't
  reflow when stance changes.
- Conviction bar — class `conviction-bar`, gradient fill proportional
  to value/10, height 8px, rounded 4px, colored per stance.
- Tier cards — class `tier-card`, hairline 1px border, `bg_2` fill,
  border-radius 12px, accent bar at top (4px, stance-colored).
- Ticker strip — class `ticker-strip`, fixed top, height 40px,
  `bg_2` background, `overflow-x: auto scroll-behavior-smooth` on
  desktop; `overflow-x: auto -webkit-overflow-scrolling: touch` on
  mobile. Each ticker item 160px min-width.
- Media queries at `@media (max-width: 768px)` — hero header/tiles
  stack vertically, conviction bar full-width, checklist one-column,
  ticker wraps onto 2 lines.

## `theme.apply_theme(fig)`

```python
def apply_theme(fig: go.Figure) -> go.Figure:
    fig.update_layout(
        paper_bgcolor=PALETTE.bg_1,
        plot_bgcolor=PALETTE.bg_1,
        font=dict(color=PALETTE.text_primary, family="Source Sans Pro"),
        xaxis=dict(gridcolor=PALETTE.gridline, zerolinecolor=PALETTE.gridline),
        yaxis=dict(gridcolor=PALETTE.gridline, zerolinecolor=PALETTE.gridline),
        hoverlabel=dict(bgcolor=PALETTE.bg_2, bordercolor=PALETTE.border,
                        font=dict(color=PALETTE.text_primary)),
        margin=dict(l=40, r=20, t=40, b=30),
        colorway=[PALETTE.primary, PALETTE.warn, PALETTE.positive, PALETTE.alert],
    )
    return fig
```

All call sites in `app.py` wrap their `st.plotly_chart(fig, ...)` as
`st.plotly_chart(apply_theme(fig), ...)`.

## Hero band helpers

### Stance pill

```python
def render_stance_pill(stance: str) -> None:
    color = {"LONG_SPREAD": PALETTE.positive, "SHORT_SPREAD": PALETTE.negative,
             "FLAT": PALETTE.text_secondary, "STAND_ASIDE": PALETTE.text_secondary
            }.get(stance, PALETTE.text_secondary)
    st.markdown(
        f'<div class="stance-pill" data-testid="stance-pill" '
        f'style="color:{color}; box-shadow: 0 0 20px {color}55;">'
        f'{stance.replace("_", " ")}</div>',
        unsafe_allow_html=True,
    )
```

### Conviction bar

```python
def render_conviction_bar(value: int, stance: str) -> None:
    pct = max(0, min(100, int(value) * 10))
    # … custom HTML with role="progressbar", aria-valuenow,
    #   data-testid="conviction-bar", and data-conviction="{value}"
```

Note: fixed attribute names so Playwright can assert. Test 99.3:
locator `[data-testid="conviction-bar"]` has `data-conviction="7"`
when the mock thesis returns conviction 7.

### Tier card

`render_tier_card(instrument, tier_key, stance)` renders:

```html
<div class="tier-card" data-testid="tier-card" data-tier="{tier_key}">
  <div class="tier-card-accent" style="background:{stance_color}"></div>
  <div class="tier-card-header">{instrument.name}</div>
  <div class="tier-card-legs">{instrument.legs}</div>
  <div class="tier-card-pl">P&L @ 1σ: ${pl_preview}</div>
  <div class="tier-card-footer">[execute stub lands here in P1.2]</div>
</div>
```

### Checklist

`render_checklist(items)` renders a `<ul class="checklist">` with each
item as `<li class="checklist-item" data-checked="true|false">` containing
an inline Lucide `check-circle` / `circle` SVG colored per state. Items
the user can toggle bind to a hidden `st.checkbox` for state; the
visible row is pure HTML.

### Catalyst countdown

`render_catalyst_countdown(hours_to_eia: float | None)` renders a
caption `"⏱ EIA release in {d}d {h}h"` in the `primary` color below
the stance pill. If `hours_to_eia is None`: render `"⏱ No scheduled
catalyst"`.

## Ticker strip

`render_ticker_strip(quotes: list[Quote])` renders at the very top of
`app.py`, above `_render_hero_band`. Each `Quote = {symbol, price,
delta_pct, delta_abs, sparkline_values}`. Delta is colored positive /
negative / muted.

The sparkline is a tiny inline `<svg viewBox="0 0 80 24">` with a
polyline of 50 values, stroked at 1.5px with the delta color. No
Plotly (that would be 3MB of JS per ticker — too heavy). Pure SVG.

The container uses `st.fragment` with a 30s refresh (already live for
the existing sparkline tiles — we reuse that fragment).

## Onboarding toasts

Tiny HTML + JS component via `st.components.v1.html`:

- On first render, reads `localStorage.getItem("mot_onboarding_done")`.
- If missing, shows the 3 toasts sequentially (8s each, fade between),
  then sets the flag.
- Messages:
  1. *"This is Aidan's oil research desk. Hover any metric for the math."*
  2. *"The hero card is the current trade thesis. Conviction tells you how strong the signal is."*
  3. *"Scroll or click the tabs for the data behind the signal."*
- ESC key or click-anywhere dismisses early.
- Height 0 (absolute-positioned), z-index 9999.

## Meta polish

- `static/logo.svg` — 64x64 oil-barrel silhouette with a small
  dislocation arrow over it. Hand-drawn SVG paths, ~30 lines.
- `static/favicon.ico` — derived via `Pillow` in a small build step
  (checked in as bytes, regenerated on demand).
- `st.set_page_config(page_title="Macro Oil Terminal — Aidan's Desk",
  page_icon="static/favicon.ico", layout="wide")`.
- Footer — single row at the very bottom of `app.py`:
  `f"Research & education only · v{BUILD_VERSION} · deployed to canadaeast"`.
  `BUILD_VERSION` reads from `git rev-parse --short HEAD` at container
  build time (baked into an env var by CD); fallback to `"dev"`.
- Remove any dev-only banners in prod — gate
  `_render_boot_check_banner` behind `STREAMLIT_ENV != "prod"` OR
  `AUTH_BANNER_IN_PROD=true` (opt-in).

## Playwright sentinels we lock today

Every polish task commits or updates these locators so future tests
stay stable:

| Sentinel | Added by |
|---|---|
| `[data-testid="stance-pill"]` | T2 |
| `[data-testid="conviction-bar"]` | T2 |
| `[data-testid="tier-card"]` (3 instances) | T2 |
| `[data-testid="checklist"]` | T3 |
| `[data-testid="catalyst-countdown"]` | T3 |
| `[data-testid="ticker-strip"]` | T4 |
| `[data-testid="onboarding-toast"]` | T8 |
| `[data-testid="app-footer"]` | T9 |

## Tests

- **Unit** — `theme.apply_theme` mutates layout fields; colour token
  fields are stable strings; `render_conviction_bar` HTML contains the
  expected `data-conviction`; palette constants match brainstorm.
- **E2E visual** — per tab + per major component, one baseline
  screenshot (1440×1800 desktop; separate 375×812 mobile). Diff
  tolerance 0.5% pixel (Playwright `to_have_screenshot({maxDiffPixelRatio:
  0.005})`). Baselines live under `tests/e2e/screenshots/`.
- **E2E DOM** — every sentinel above gets a `locator().count() == N`
  assertion in a new `test_ui_polish_sentinels.py`.

## What we explicitly do NOT do in this pass

- Layout refactor (tabs → single-scroll + sticky nav). Logged as
  "UIP-P2 layout review" for after merge.
- Replace Streamlit with a different framework.
- Add any analytics / telemetry.
- Change the quantitative logic of any model.
- Rework the Alpaca / auth modules (those live in other branches /
  phases).

## Acceptance criteria

- All 10 polish tasks green (unit + e2e).
- Visual regression suite passes on desktop + mobile.
- Warm TTI ≤ 2s, cold ≤ 4s (measured via Playwright helper).
- Before + after screenshots attached to the finishing-flow PR.
- Live canadaeast deploy renders with the new theme and no
  console errors.

## Reversibility

- Nuke `theme.py` + delete the CSS injection line in `app.py` →
  back to stock Streamlit look.
- Swap palette colours → edit one dataclass.
- Roll back the whole pass via `git revert <merge-sha>` — single
  atomic undo.

---

## Corrections (2026-04-22 01:05Z): branding + deep language pass

### New module: `language.py`

```
language.py
  TERMS                       # frozen mapping: old-key -> display string
  describe_stretch(value)     # float -> "Calm"/"Normal"/"Stretched"/...
  describe_confidence(i)      # int 1-10 -> "Low"/"Medium"/"High"/"Very High"
  describe_correlation(r)     # float -> "Weak"/"Moderate"/"Strong"
  describe_stance(stance)     # LONG_SPREAD -> "Buy the spread", etc.
  with_tooltip(term_key)      # returns (display_name, help_text) pair
```

`TERMS` is the single source of truth. Every render site goes through
it (or through one of the `describe_*` helpers). No bare "thesis",
"dislocation", "Z-score", "conviction", etc. in UI copy — every one
of those strings comes out of `language.TERMS` or a `describe_*` call.

### Rename table (authoritative — UIP-T0 implements)

| Key in `TERMS` | Old UI term | New UI term |
|---|---|---|
| `trade_idea` | Thesis / Trade Thesis | **Trade idea** |
| `stretch` | Dislocation | **Spread Stretch** |
| `stretch_alert` | Z-score alert threshold | **Alert when stretched this much** |
| `stretch_series` | 90-day dislocation | **How the stretch has moved over the last 90 days** |
| `stretch_extreme` | Extreme dislocation | **Very extreme stretch** |
| `std_unit` | Standard deviation | **times the usual daily move** |
| `mean_reversion` | Mean reversion | **Snap-back to normal** |
| `backtest_label` | Historical backtest | **How this strategy would have worked in the past** |
| `sharpe` | Sharpe ratio | **Risk-adjusted return** |
| `drawdown` | Max drawdown / biggest losing streak | **Worst drop during a losing run** |
| `vol` | Volatility | **How jumpy prices are** |
| `depletion` | Depletion rate | **How fast stocks are running down (barrels/day)** |
| `floor_breach` | Inventory floor breach | **When stocks run out** |
| `floor` | Floor | **Low point / red line** |
| `flag_state` | Flag state | **Country the ship is registered in** |
| `jones_act` | Jones Act / Domestic | **US-flagged or US-bound** |
| `shadow_risk` | Shadow Risk | **Flags of convenience (Panama, Liberia, …)** |
| `sanctioned` | Sanctioned | **Sanctioned-country flags (Russia, Iran, Venezuela)** |
| `materiality` | Materiality | **Whether anything changed meaningfully** |
| `catalysts` | Catalyst watchlist | **What could move the market next** |
| `invalidations` | Invalidation risks / What would make us wrong | **What would break this trade idea** |
| `confidence` | Conviction | **Confidence** |
| `long_spread` | Long spread | **Buy the spread** |
| `short_spread` | Short spread | **Sell the spread** |
| `flat` | Flat / Stand aside | **Wait** |

**Advanced-view only** (never default surface; reached via the existing
"Advanced metrics" toggle): Z-score, cointegration, half-life, GARCH,
hedge ratio. Tooltip text for any renamed term still names the
technical concept so a finance-literate reader can map back.

### Qualitative bands (frozen)

```python
def describe_stretch(abs_z: float) -> str:
    if abs_z < 0.7:  return "Calm"
    if abs_z < 1.3:  return "Normal"
    if abs_z < 2.3:  return "Stretched"
    if abs_z < 3.2:  return "Very Stretched"
    return "Extreme"

def describe_confidence(n: int) -> str:
    if n <= 3: return "Low"
    if n <= 6: return "Medium"
    if n <= 8: return "High"
    return "Very High"

def describe_correlation(r: float) -> str:
    a = abs(r)
    if a < 0.3: return "Weak"
    if a < 0.6: return "Moderate"
    return "Strong"
```

Display contract: the raw number sits next to the label, separated by
a colon or space. `Stretched: 2.4× normal`. `Confidence: High (7/10)`.
`Correlation: Strong (0.71)`. Label carries the meaning; number is
for precision-seekers.

### Tooltip contract

Every renamed metric's `help=` string on `st.metric`, `st.slider`,
`st.caption` etc. keeps the technical term and explains the math.
Template:

> *Also called **<technical term>**. <One-sentence plain-English
>  definition>. <One-sentence on how to read the current value>.*

Example:

> *Also called **Z-score** or **dislocation**. This measures how far
>  today's spread is from its normal range, expressed as multiples of
>  the usual daily move. 2.4 means the spread is 2.4× its usual wobble
>  above average — statistically unusual.*

All tooltips live next to `TERMS` in `language.py` so they update in
lockstep. Tests assert that every `TERMS` key has a corresponding
tooltip.

### Trade-idea schema change — `plain_english_headline`

`trade_thesis.THESIS_JSON_SCHEMA` grows one required string field:

```json
"plain_english_headline": {
  "type": "string",
  "description": "One sentence, anyone-understands. No jargon. State what's happening in the market in plain words and one concrete suggestion if relevant. Max 30 words."
}
```

The LLM prompt in `trade_thesis.py::_build_prompt` adds an instruction:

> *First, write a one-sentence headline a non-finance reader would
>  understand. No jargon. Example: "Brent is trading unusually
>  expensive vs WTI right now. This kind of gap usually closes within
>  3 weeks, so it's a good moment to bet on the gap narrowing."*

The `Thesis` dataclass grows `plain_english_headline: str = ""`
(default empty for grandfathered rows in `data/trade_theses.jsonl`
that predate the schema).

Hero rendering order becomes:

```
┌─────────────────────────────────────────────────────────────┐
│ "Brent is trading unusually expensive vs WTI right now..." │  ← plain_english_headline
├─────────────────────────────────────────────────────────────┤
│ [ STAND ASIDE ]  ⏱ EIA release in 2d 14h                   │  ← stance pill + countdown
├─────────────────────────────────────────────────────────────┤
│ Confidence: High (7/10)  ▓▓▓▓▓▓▓░░░                        │  ← conviction bar
├─────────────────────────────────────────────────────────────┤
│  [Tier 1 card]  [Tier 2 card]  [Tier 3 card]               │  ← instrument tiles
├─────────────────────────────────────────────────────────────┤
│  ☑ Stop in place   ☑ Size within cap   ☐ Half-life read   │  ← checklist
└─────────────────────────────────────────────────────────────┘
```

### Branding strip

- `st.set_page_config(page_title="Macro Oil Terminal", page_icon=LOGO_PATH)`.
- Footer: `f"Research & education only · v{BUILD_VERSION} · canadaeast"`.
  No name.
- README: title stays `Macro Oil Terminal`; strip any first-person /
  "my / I / Aidan" phrasing from prose.
- Zero personal greetings in-app.

### Test delta from T0

New unit tests in `tests/unit/test_language.py`:

1. `test_describe_stretch_bands` — parametrised (0.5→"Calm", 1.0→"Normal",
   2.0→"Stretched", 3.0→"Very Stretched", 4.0→"Extreme").
2. `test_describe_confidence_bands` — 1→"Low", 5→"Medium", 7→"High",
   10→"Very High".
3. `test_describe_correlation_bands` — 0.1→"Weak", 0.4→"Moderate",
   0.8→"Strong" (absolute value).
4. `test_terms_has_tooltip_for_every_key` — iterate `TERMS`, assert a
   non-empty tooltip exists for each.
5. `test_no_old_terms_in_terms_values` — assert none of the display
   strings contain "thesis", "dislocation", "Z-score", "conviction"
   (belt-and-braces — stops regressions).

New unit test in `tests/unit/test_trade_thesis.py`:

6. `test_thesis_schema_includes_plain_english_headline` — schema dict
   has the field in its `required` list.

Updated e2e assertion in `tests/e2e/test_hero_band.py`:

- Swap "Dislocation" → "Spread Stretch" sentinel.
- Swap "Conviction" → "Confidence".
- Swap "Stand aside" → "Wait" / "STAND ASIDE" → "WAIT".
- Add `[data-testid="plain-english-headline"]` attached check.

Updated e2e assertion in `test_auth_public_and_gated.py` and
`test_dashboard_smoke.py`:

- Any hard-coded old label string → use the new one.

### UIP-T0 task ordering

T0 lands first because every downstream visual task (T2 hero, T3
checklist, T5 charts, T6 mobile, T9 meta) references the renamed
constants. Fresh subagent, RED (new tests fail) → GREEN (land
`language.py` + rename in `app.py` + update existing tests) →
REFACTOR → commit.

### Acceptance test

The "non-finance friend" screenshot test: after UIP-T9 meta polish
ships, one of the before/after screenshots gets a caption saying
*"A friend with no finance background read this without questions."*
If that caption can't be written truthfully, UIP-T0 didn't land.

