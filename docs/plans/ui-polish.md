# UI polish pass — Plan

> **Status:** APPROVED (2026-04-22 01:05Z with T0 language pass baked in).
> **Branch:** `feat/ui-polish-pass` off `main`, worktree at
> `../macro_oil_terminal-ui-polish`.
> **Rhythm:** fresh subagent per task, RED→GREEN→REFACTOR→commit.
> Visual-only tasks gate on Playwright screenshot diffs (tolerance
> `maxDiffPixelRatio: 0.005`).

## Definition of done

- Theme palette + CSS injection shipped, applied to every chart.
- Hero band (stance pill, conviction bar, tier cards, checklist,
  catalyst countdown) restyled using renamed terminology.
- Ticker strip above hero, Bloomberg-tape style.
- Every finance term renamed via `language.TERMS` with tooltips
  preserving the technical terminology.
- `plain_english_headline` field lands on `Thesis` schema + rendered
  as the top line of the hero card.
- Mobile (375×812) and desktop (1440×1800) visual regression
  baselines checked in.
- First-visit onboarding toasts.
- Logo SVG + favicon + `Macro Oil Terminal` title (generic, no
  personalization) + footer with version + region only.
- Warm TTI ≤ 2s verified with before/after Playwright measurement.
- Before + after screenshots of hero / macro / depletion / fleet /
  mobile attached to finishing-flow PR.
- `data/trade_theses.jsonl` + `trade_thesis.Thesis` grow
  `plain_english_headline` with a grandfathered empty-string default.

---

## Task T0 — Language pass (scaffolding; blocks T2–T9)

**Red** — add `tests/unit/test_language.py`:

1. `test_describe_stretch_bands` — 0.5→Calm, 1.0→Normal, 2.0→Stretched,
   3.0→"Very Stretched", 4.0→Extreme.
2. `test_describe_confidence_bands` — 1→Low, 5→Medium, 7→High,
   10→"Very High".
3. `test_describe_correlation_bands` — 0.1→Weak, 0.4→Moderate, 0.8→Strong;
   negative values use absolute.
4. `test_terms_has_tooltip_for_every_key` — iterate `TERMS.keys()`,
   assert `with_tooltip(key)` returns a non-empty `help_text`.
5. `test_no_old_terms_in_terms_values` — none of the display strings
   contain "thesis", "dislocation", "Z-score", "conviction",
   "standard deviation", "volatility", "Sharpe ratio", "Jones Act",
   "shadow risk", "cointegration", "half-life".

Plus one schema test in `tests/unit/test_trade_thesis.py`:

6. `test_thesis_schema_includes_plain_english_headline` — the schema
   dict's `required` list includes the new field.

**Green** — create `language.py` with the authoritative rename table
from the design spec, the three `describe_*` helpers, and
`with_tooltip(key)`. Add `plain_english_headline: str = ""` default
to `Thesis` dataclass. Add the required field + prompt instruction to
`trade_thesis.py`. Update every hard-coded UI string in `app.py` that
collides with the rename table to pull from `language.TERMS` or
`describe_*`.

**Also update existing tests that assert old labels:**
- `tests/e2e/test_hero_band.py` — swap "Dislocation" / "Conviction" /
  "Stand aside" sentinels.
- `tests/e2e/test_auth_public_and_gated.py` — any "Sign in with
  Google" → just "Sign in" (auth is archived), plus any old labels.
- `tests/e2e/test_dashboard_smoke.py` — sweep.
- `tests/e2e/test_thesis_flow.py` — sweep (and the known hang on
  first test is *not* in scope to fix here; just swap strings).
- `tests/unit/test_trade_thesis.py` — any "thesis"-literal in the
  test's own copy (not code under test names) stays; only UI-copy
  assertions swap.

**Refactor** — one pass over `app.py` consolidating copy into a single
section that pulls from `language.TERMS` so reviewers can skim a
diff of before/after copy in one place.

**Commit:** `feat(ui): language pass — rename finance jargon to plain English (UIP-T0)`.

Expected pytest delta: +6 new tests, -0 / +N e2e-assertion string
swaps. Target: full suite passes.

---

## Task T1 — theme module + palette + CSS injection

**Red** — `tests/unit/test_theme.py`:

1. `test_palette_is_frozen_dataclass` — assertion.
2. `test_palette_hex_tokens_match_brainstorm` — each token has the
   exact string from the brainstorm's table.
3. `test_inject_css_writes_style_tag` — call `inject_css()` with a
   mocked `st.markdown`; assert called with `<style>...</style>` and
   that the CSS contains `.stance-pill`, `.conviction-bar`,
   `.tier-card`, `@media (max-width: 768px)`.
4. `test_inject_css_is_idempotent_within_session` — two calls with a
   shared mock `session_state`; `st.markdown` called exactly once.

**Green** — create `theme.py` with `PALETTE` dataclass + `inject_css()`
+ module-level `_CSS` constant. Update `.streamlit/config.toml`
with the dark base + primary cyan from the design spec. Call
`theme.inject_css()` at the top of `app.py` (right after
`st.set_page_config`).

**Commit:** `feat(ui): theme palette + CSS injection (UIP-T1)`.

---

## Task T2 — Hero polish (stance pill + conviction bar + tier cards)

Depends on T0 (for "Confidence" / "Buy the spread" etc) + T1 (for the
palette).

**Red** — `tests/unit/test_theme_hero.py`:

1. `test_render_stance_pill_emits_data_testid` — mock `st.markdown`;
   call with `"LONG_SPREAD"`; captured HTML has `data-testid="stance-pill"`
   and contains the translated display string (from `language.TERMS`).
2. `test_render_conviction_bar_reflects_value` — call with value=7;
   HTML contains `data-conviction="7"` and a `role="progressbar"`.
3. `test_render_tier_card_includes_pl_preview` — render with an
   `Instrument` stub; HTML contains `data-testid="tier-card"`,
   `data-tier="tier1"`, and a P&L preview string `$`-prefixed.

Plus one e2e in `tests/e2e/test_ui_polish_sentinels.py` (new):

4. `test_hero_sentinels_attached_unauthed` — navigate, assert
   `[data-testid="stance-pill"]`, `[data-testid="conviction-bar"]`,
   and three `[data-testid="tier-card"]` all attached.

**Green** — move the stance / conviction / tier-card rendering out of
`app.py` into `theme.py` helpers per the design spec. Delete the old
inline Streamlit widgets that previously rendered them.

**Commit:** `feat(ui): restyled hero (stance pill + conviction bar + tier cards) (UIP-T2)`.

---

## Task T3 — Styled checklist + catalyst countdown

Depends on T0 (tooltip copy) + T1 (palette).

**Red** — `tests/unit/test_theme_checklist.py`:

1. `test_render_checklist_emits_styled_list` — mock HTML capture;
   assert `<ul class="checklist">` and one `<li data-checked>` per
   item, plus an inline SVG.
2. `test_render_catalyst_countdown_formats_days_hours` — 62.5h →
   `"⏱ 2d 14h"`; 5h → `"⏱ 0d 5h"`; None → `"No scheduled catalyst"`.

Plus one e2e sentinel:

3. `test_checklist_and_countdown_attached` — both data-testids
   attached on the hero.

**Green** — implement `theme.render_checklist(items)` and
`theme.render_catalyst_countdown(hours_to_eia)`.

**Commit:** `feat(ui): styled checklist + EIA countdown (UIP-T3)`.

---

## Task T4 — Ticker strip (Bloomberg tape)

Depends on T1.

**Red** — `tests/unit/test_theme_ticker.py`:

1. `test_render_ticker_strip_emits_one_item_per_quote` — 4 quotes in,
   4 `.ticker-item` blocks out.
2. `test_ticker_sparkline_uses_delta_color` — positive delta → stroke
   color is `PALETTE.positive`; negative → `PALETTE.negative`.
3. `test_ticker_item_attaches_data_symbol` — each item has
   `data-symbol="BZ=F"` etc.

Plus e2e sentinel:

4. `test_ticker_strip_renders_above_hero` — `[data-testid="ticker-strip"]`
   attached AND its bounding-box `y` is less than the hero-band
   bounding-box `y`.

**Green** — implement `theme.render_ticker_strip(quotes)` using inline
SVG sparklines (no Plotly). Move the ticker call above
`_render_hero_band` in `app.py`.

**Commit:** `feat(ui): Bloomberg-style ticker strip above hero (UIP-T4)`.

---

## Task T5 — apply_theme(fig) + chart polish

Depends on T0 (axis labels) + T1 (palette).

**Red** — `tests/unit/test_theme_charts.py`:

1. `test_apply_theme_sets_palette_colors` — assert `paper_bgcolor`,
   `plot_bgcolor`, `font.color`, `xaxis.gridcolor`, `yaxis.gridcolor`.
2. `test_apply_theme_sets_colorway_to_primary_then_warn` — colorway[0]
   is primary hex.
3. `test_apply_theme_margins` — `margin.l/r/t/b` match design-spec values.

No new e2e — visual regression captures the rest.

**Green** — implement `theme.apply_theme(fig)` per design spec. Wrap
every `st.plotly_chart(fig, ...)` in `app.py` as
`st.plotly_chart(apply_theme(fig), ...)`. Rename axis labels that
still read snake_case — `spread_usd → "Spread ($)"`, etc. — using
constants from `language.TERMS`. Update hover templates to use
plain-English labels and `$%.2f` formatting.

**Commit:** `feat(ui): apply_theme(fig) + chart axis/hover polish (UIP-T5)`.

---

## Task T6 — Mobile viewport pass

Depends on T1–T5.

**Red** — `tests/e2e/test_ui_polish_mobile.py`:

1. `test_mobile_hero_stacks` — 375×812 viewport; assert
   `ticker-strip.y < stance-pill.y < tier-card[0].y < tier-card[1].y`
   (vertical stack).
2. `test_mobile_no_horizontal_scroll` — `page.evaluate("document.body.scrollWidth <= window.innerWidth + 1")`.
3. `test_mobile_sidebar_collapsed_by_default` — the Streamlit
   collapsed-sidebar hamburger is visible; sidebar content is not.

**Green** — iterate on the `@media (max-width: 768px)` block in
`theme._CSS` until all three pass. Screenshots captured as goldens in
`tests/e2e/screenshots/hero_mobile.png`.

**Commit:** `feat(ui): mobile viewport (375×812) polish (UIP-T6)`.

---

## Task T7 — Loading + empty + error states

Depends on T1.

**Red** — `tests/unit/test_theme_states.py`:

1. `test_render_empty_with_icon_and_message` — captured HTML contains
   the inline SVG + the message string.
2. `test_render_error_includes_retry_button` — captured HTML contains
   `Retry now` button text and the error message (not a raw
   traceback).
3. `test_render_loading_status_uses_native_primitive` — wraps
   `st.status` so `expanded=False` by default.

No new e2e.

**Green** — implement `theme.render_empty(icon, message)`,
`theme.render_error(message, retry_fn)`, `theme.render_loading_status(label)`.
Audit `data_ingestion.py` + `providers/*.py` public functions; wrap
raising paths in try/except that returns a typed result
`{ok: bool, data|error_message, retry_fn_hint}`. Every call site in
`app.py` routes errors through `render_error`.

**Commit:** `feat(ui): loading/empty/error state primitives (UIP-T7)`.

---

## Task T8 — First-visit onboarding toasts

Depends on T1.

**Red** — `tests/unit/test_theme_onboarding.py`:

1. `test_render_onboarding_emits_three_messages` — mock
   `st.components.v1.html`; captured HTML contains each of the three
   messages (parametrised).
2. `test_onboarding_html_reads_localstorage` — captured HTML contains
   `localStorage.getItem("mot_onboarding_done")`.
3. `test_onboarding_html_dismisses_on_esc` — the inline JS binds to
   `keydown` and checks `key === "Escape"`.

E2E sentinel:

4. `test_onboarding_toast_attaches_on_first_visit` — navigate with a
   fresh context (no localStorage), assert
   `[data-testid="onboarding-toast"]` attached.

**Green** — implement `theme.render_onboarding()` using
`st.components.v1.html`. Call once at the top of `app.py`. Wording
matches the design spec.

**Commit:** `feat(ui): first-visit onboarding toasts (UIP-T8)`.

---

## Task T9 — Meta polish (logo + favicon + title + footer)

Depends on T0 (no personalization in any copy) + T1 (footer colors).

**Red** — `tests/unit/test_theme_meta.py`:

1. `test_logo_svg_file_present_and_nonempty` — `pathlib.Path("static/logo.svg")`
   exists, > 200 bytes, contains `<svg`.
2. `test_favicon_file_present_and_nonempty` — `static/favicon.ico` > 200
   bytes.
3. `test_build_version_resolver` — reads `BUILD_VERSION` env var,
   falls back to `"dev"`.
4. `test_footer_never_contains_personal_strings` — parametrised over
   `{"aidan", "Aidan", "youbiquity", "personal"}`; footer HTML
   contains none.

E2E sentinel:

5. `test_page_title_is_generic` — `page.title() == "Macro Oil Terminal"`.
6. `test_footer_sentinel_attached` — `[data-testid="app-footer"]`
   attached AND its text matches `/^Research.+v.+canadaeast$/`.

**Green** — draw `static/logo.svg`, render to
`static/favicon.ico` via a tiny build script checked in at
`infra/gen_favicon.py`. Update `st.set_page_config(page_title="Macro Oil Terminal", page_icon="static/favicon.ico")`.
Add `render_footer(version, region)` to `theme.py` and call it once
at the bottom of `app.py`. Gate the boot-check banner behind
`STREAMLIT_ENV != "prod"` unless `AUTH_BANNER_IN_PROD=true`.

**Commit:** `feat(ui): logo + favicon + generic title + footer (UIP-T9)`.

---

## Task T10 — Performance + before/after screenshot pack

Depends on T1–T9.

- `.agent-scripts/measure_tti.py` captures warm + cold TTI and
  first-paint for the current deploy; writes a JSON line to
  `docs/perf/ui_polish_deltas.md`.
- Run once against a pre-merge main checkout for "before" baseline
  (we have the pre-polish HEAD at c79fc20).
- Run against the polished `feat/ui-polish-pass` tip for "after".
- Capture the five Playwright screenshots listed in the design spec
  under `docs/screenshots/after/`.
- README gets a new section "Latest UI (v0.4)" with a 2-up
  before/after for hero only; full set links into `docs/screenshots/`.

No new tests — this is a measurement and capture task.

**Commit:** `docs(ui): perf measurement + before/after screenshots (UIP-T10)`.

---

## Task T11 — Finishing flow

1. Merge `main` into `feat/ui-polish-pass`; resolve if any (unlikely).
2. Full suite locally — unit + e2e + visual regression.
3. Playwright warm screenshot of desktop + mobile; eyeball each.
4. Push; CI green.
5. `git merge --no-ff feat/ui-polish-pass` to main. Push.
6. CD to canadaeast; live verify — take the 5 screenshots against
   the live deploy; attach to PROGRESS.md.
7. Delete worktree + branch (local + remote).
8. PROGRESS.md block.

**Commit (merge):** `Merge feat/ui-polish-pass: theme + language + hero + ticker + mobile (UIP)`.

---

## Open risks

- **Visual regression baselines drift.** If a chart's render varies by
  data-date, the screenshot diff fails flakily. Mitigation: freeze
  `E2E_FREEZE_DATE=2026-04-22` env that `data_ingestion.py` honours to
  return a canned fixture instead of live network. Added as part of
  T6.
- **Streamlit session_state cross-fragment collisions.** The ticker
  uses `@st.fragment(run_every="30s")` already; adding more fragments
  risks weird rerun cycles. Mitigation: keep fragment scope narrow
  and measured in T4.
- **Boot-check banner in prod.** P1.1's banner logic still runs; we
  gate it in T9 to only show in dev.
- **Language pass + LLM**: the LLM needs a new `plain_english_headline`
  field; if the prompt isn't explicit, the model may truncate or
  over-jargonify. Mitigation: one-shot example in the prompt, plus a
  post-validation fallback that generates a simple template headline
  from stance+stretch_band if the LLM's is empty or >30 words.

