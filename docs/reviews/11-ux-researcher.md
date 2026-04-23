# 11 — UX researcher review (Macro Oil Terminal)

> Reviewer persona: senior product designer / UX researcher, 10+ years
> at consumer-facing data products (Robinhood, Wealthfront, Palantir
> Foundry). Lands on `https://oil-tracker-app-canadaeast-4474.azurewebsites.net`
> cold, pretends never to have seen it, and tries to figure out what
> the product is and what to do in 30 seconds.

---

## Methodology

Captured 2026-04-22 against the live-deployed Azure app (no local
boot) using host Playwright. Scripts + PNGs in
`/Users/aidanbothost/Documents/macro_oil_terminal/docs/reviews/ux-evidence/`.
40+ PNGs across iPhone 13 (375 × 812, Mobile Safari UA), Pixel 7
(412 × 915, Chrome Android UA), desktop (1440 × 900) — landing + each
of three tabs + interactive states (slider, "Show advanced metrics",
sidebar). Five annotated via PIL (`annotate.py`).

`capture_scroll2.py` / `capture_tabs_deep.py` walk the Streamlit inner
scroll container (`section.stMain` scrollHeight = 3002 px desktop
landing, **6003 px iPhone landing — 7 mobile viewports tall**).

**DOM scans** (`_dom_{viewport}.json`, per viewport × tab): unique
`computedStyle.fontSize` counts, every `button / a / [role=tab] /
input[type=range] / summary` bounding box with `w<44 || h<44`
flagged, `body.scrollWidth vs innerWidth`, and a contrast walk
(`color` vs first opaque-bg ancestor, WCAG 2.1 luminance, flag < 4.5:1).
Where the walker returned identical fg/bg rgb (parser artifact on
alpha-blended surfaces) I did manual hex→luminance spot checks and
note so inline. Playwright runs Chromium, not WebKit — honest
iOS-rendering caveat.

---

## First-30-seconds comprehension — **4/10**

Cold on desktop (`desktop_landing.png`, `desktop_landing_annotated.png`):
eye lands on the 280 px sidebar of controls I haven't earned the right
to care about; then on the **36 px headline "Inventory-Adjusted Spread
Arbitrage & AIS Fleet Analytics"** — 10 words of jargon that signal
who it's for (Brent/WTI quants) but not what to do; then on a
decorative WebGL "signal flow" banner that looks like a chart and
encodes nothing.

The answer to "what is this" is split across **two competing verdict
surfaces**: a chip labelled `HERO · STAND ASIDE` and, 200 px below,
the full verdict card (amber confidence bar, "horizon 28 days",
driver bullets). The word `HERO ·` is a layout tag that shipped as
user-visible copy. Two verdicts stacked in the same hero block,
worded differently, is the single biggest 30-second tax.

Mobile is worse: `iphone13_landing.png` — the entire above-the-fold
is headline + a "trade idea not yet generated" chip; **no prices, no
gauge, no verdict visible** until scroll. On Pixel 7
(`pixel7_overflow_annotated.png`) the inline metric row ends mid-word
"…WTI $92.96 sp". The product's job — "should I trade Brent-WTI
today?" — becomes intelligible after ~45 s of scrolling.

## Information hierarchy — **3/10**

Eye-order on desktop first paint: (1) sidebar "Controls", (2) the 36 px
headline, (3) WebGL banner, (4) 4-up ticker row, (5) finally STAND
ASIDE (`desktop_scrollA_1.png`). Nothing says "this is the answer,
that is supporting evidence." The chip literally labelled `HERO` is
*not* the hero; the real verdict card is demoted below the headline.

The tab bar (`Spread Stretch / Inventory drawdown / Tanker fleet`)
sits **below** the hero — y ≈ 1760 desktop, y ≈ 4500 iPhone 13
(`desktop_scrollA_1.png`, `iphone13_invD_3.png`). Every tab switch
requires scrolling past the hero; tabs-at-the-bottom inverts
convention.

## Mobile usability — **3/10**

All numbers below from `_dom_iphone13.json` / `_dom_pixel7.json`.

**Tap targets < 44 × 44** (WCAG 2.5.5 / Apple HIG minimum) —
31 on iPhone 13 landing, 39 on Pixel 7. Representative:

| Target | Measured | Note |
|---|---|---|
| `stExpandSidebarButton` (`»` icon to open sidebar) | **28 × 28** | sole access path to every control on mobile |
| `stSidebarCollapseButton` | 28 × 28 | |
| 6 × "Help for …" info icons in sidebar | **16 × 16 each** | ¼ of minimum area |
| `stBaseButton-header` ("Stop") | 47 × **28** | also a trust issue, see below |
| `stMainMenuButton` (hamburger) | 28 × 28 | |

The 28 × 28 chevron is the **single gate to every control** on mobile
(`iphone13_sidebar_open_fixed.png`) — ~60 % under the 44 × 44 area
minimum. No swipe-from-edge fallback; DOM confirms collapsed sidebar
at `x = -300 px`.

**Horizontal overflow**: `body.scrollWidth == innerWidth` on all three
viewports. But **visual clipping** is present:
`pixel7_overflow_annotated.png` E1 — the inline "confidence · Brent ·
WTI · spread · stretch · next EIA" row is non-wrapping text inside a
narrower column, so the tail is severed rather than wrapped.

The 36 px H1 wraps to 3 lines on both 375 px and 412 px
(`iphone13_landing_annotated.png` A1). Should cap ~22 px on mobile.

Open sidebar overlays 280 px of 375 px (`iphone13_sidebar_open_fixed.png`):
a user adjusting "Alert when stretched" can't see the chart that
slider controls — three-tap round trip per parameter change.

## Desktop usability — **6/10**

Only dimension crossing "meets baseline." Ticker fits
(`desktop_landing.png`), Brent/WTI chart is legible
(`desktop_scrollA_2.png`), sidebar at 19 % of viewport is reasonable.

Stops it reaching a 7: prose paragraphs run full-width at ~140 cpl
(`desktop_invD_1.png`) — 55-75 cpl upper bound violated. 5 KPI tiles
on the Spread Stretch tab spread edge-to-edge with identical visual
weight (`desktop_spread_annotated.png` D2); nothing anchors a hero
metric. Whitespace between blocks is thin (Streamlit's 24 px default).

## Visual language consistency — **5/10**

From `_dom_desktop.json`:

- Heads `#ffffff` on `#0b0f14` — ~19:1. Fine.
- Muted body `rgb(154,164,184)` on same base — 7:1. Fine.
- **Cyan `#22d3ee` does four jobs**: Sign-in button, live-mode
  toggle, slider fills, slider value labels. The cyan `3.00/300/4`
  slider bubbles land directly on the filled cyan track —
  functionally unreadable when positioned over the filled section.
- Positive deltas `#a3e635` lime; amber progress `#f59e0b`; warning
  blocks re-use that amber at ~12 % alpha. Manual check on amber-
  on-amber: `#f59e0b` over `#0b0f14` with 12 % amber tint ≈ 4.8:1 —
  scrapes AA, reads muddier because tint compresses contrast.
- **10 unique font sizes on one page** (14, 12, 16, 14.72, 13, 14.08,
  20, 24, 36, 13.6). Fractional sizes are unset rem defaults.
- **Material icon literal strings** leak through —
  `keyboard_double_arrow_left`, `keyboard_arrow_right` appear as raw
  text on elements where the icon font's ligature hasn't applied.
- Three border-radius scales in play (4 / 8 / 12 + pill).

## Chart readability — **6/10**

The Brent-vs-WTI chart on the Spread Stretch tab (`desktop_scrollA_2.png`)
is the strongest visual asset: dual-axis, colour-distinct lines,
subtle gridlines, date-range selector. Legend top-right is standard.

Issues: tile values mix decimal precision inconsistently (`$101.91`
next to `1.01` hedge ratio next to `WEAK` categorical, all at
identical rank — `desktop_spread_annotated.png` D2); the 90-day
spread-stretch plot (`desktop_scrollA_3.png`) has no y-axis title or
unit label and the x-axis is just timestamps; and the hero WebGL
"signal flow" banner is **decoration that looks like data** — a quant
glancing from across the room would mistake its colours for a regime
signal. That's the single most Palantir-like mistake in the app.

## Cognitive load — **4/10**

First-paint element count on desktop landing
(`desktop_landing.png`): **22+ distinct elements** — title, tagline,
toggle + 3 sliders + 2 toggles + expander + 2 header buttons (sidebar),
4 ticker tiles × 3 sub-elements, WebGL banner, `HERO · STAND ASIDE`
chip, Sign-in CTA, "No actionable catalyst" banner, amber warning
block, 6 "?" help icons. A Robinhood-style product lands at 6-8.
Bloomberg density without the Bloomberg keyboard vocabulary.

Progressive disclosure is attempted — "Show advanced metrics" swaps
in instrument-level charts (`desktop_advanced_toggled.png`). Right
instinct; wrong default. Landing defaults to "everything."

## Trust signals — **4/10**

Erodes trust:

- **"Stop" button top-right** is Streamlit's dev script-runner
  (`desktop_landing.png`; DOM `stBaseButton-header`). Prod users see it.
- **"execute — wiring"** placeholder on every ETF pair card
  (`desktop_invD_1.png`) — half-finished copy shouting "beta."
- **"trade idea not yet generated"** chip persists when a verdict
  actually exists (`iphone13_landing.png`).
- **"HERO ·"** as user-visible copy — layout comment that escaped.
- **No freshness timestamp above the fold**. The `Source: yfinance …
  fetched 2026-04-23 21:19:47Z` line is buried at the bottom of the
  chart on tab 1 (`desktop_scrollA_2.png`). A terminal lives on
  "as-of" metadata.
- Disclaimer paragraph shares font size with adjacent data.

Nudges trust back: explicit `Drivers:` bullets citing Z-score /
cointegration / inventory, the Confidence bar with horizon, and the
data-source footer (yfinance / EIA / AIS) are substantive. The
substance is there; the surface undersells it.

## Error / empty / loading states — **5/10**

- **Loading banner** `✓ Loading live market data…` persists at top of
  every viewport at first paint (`desktop_landing.png`,
  `iphone13_landing.png`, `pixel7_landing.png`) — never cleared in my
  30 s windows. Reads as "broken."
- **Empty state** "No actionable trade idea today. Monitor the Spread
  Stretch gauge above." + in-tray illustration (`desktop_invD_1.png`)
  — well-written, on-brand.
- **Error state**: not triggered; the amber "data subject to
  reporting delays" soft warning is well-positioned.
- **Placeholders** ("TBD", "execute — wiring", "P&L @ 1σ: —") undercut
  the empty-state polish.

## Mobile-specific breakage — 7 items

1. **28 × 28 sidebar-open chevron**, sole access to all controls,
   no swipe fallback (`iphone13_sidebar_open_fixed.png`).
2. **6 × 16 × 16 help-tooltip icons** in the sidebar.
3. **Metric row clips** on Pixel 7: `pixel7_overflow_annotated.png` E1 —
   "…WTI $92.96 sp" severed mid-word.
4. **36 px H1** consumes the entire above-the-fold on 375 px
   (`iphone13_landing_annotated.png` A1); no price, gauge, or verdict
   visible.
5. **Tab strip at y ≈ 4500 px** on iPhone 13 (`iphone13_invD_3.png`);
   average user won't discover tab 2/3.
6. **"Sign in with Google" dominates the verdict** on mobile
   (`iphone13_signin_annotated.png` B1/B2) — white on cyan contrast
   1.81:1, and it's the highest-chroma element on screen.
7. **Open sidebar covers 80 %** of a 375 px screen
   (`iphone13_sidebar_open_fixed.png`): three-tap round trip per
   parameter change.

## Top-15 ranked findings — by decibel of harm

| # | Severity | Issue | Evidence | Fix proposal |
|---|---|---|---|---|
| 1 | Critical | `HERO · STAND ASIDE` chip ships a layout tag as copy; duplicates the real verdict card 200 px below | `desktop_landing_annotated.png` C4; `iphone13_signin_annotated.png` B3 | Delete the chip. Promote the full verdict card (amber bar + confidence + horizon) to the actual hero, above the 36 px title |
| 2 | Critical | "trade idea not yet generated" chip persists even when a verdict exists | `iphone13_landing.png`; chip colour `#0b0f14` on `#444a54` = 2.15:1 (AA fail) | Remove or wire to real state; verdict card's empty-state handles no-signal |
| 3 | Critical | Sidebar-open chevron 28 × 28 on mobile; only access to all controls | `iphone13_sidebar_open_fixed.png`; DOM `stExpandSidebarButton` | 44 × 44 hit target with transparent pad; add swipe-from-left gesture |
| 4 | Critical | "Sign in with Google" out-ranks the trade verdict visually on mobile | `iphone13_signin_annotated.png` B1/B2; white on cyan = 1.81:1 (AA fail) | Demote to icon-only link in header. App is usable without auth, so CTA shouldn't live in hero |
| 5 | Critical | Streamlit dev `Stop` button visible in prod top-right | `desktop_landing.png`; DOM `stBaseButton-header` | Ship with `menuItems=None`, `developmentMode=False`; hide the running-man icon |
| 6 | High | Tab strip rendered below hero (y ≈ 1760 desktop / ≈ 4500 iPhone) — every switch requires scroll | `desktop_scrollA_1.png`, `iphone13_invD_3.png` | Move tabs above hero, or repaint hero per tab context |
| 7 | High | "execute — wiring" placeholder on all three ETF pair cards | `desktop_invD_1.png`, `iphone13_invB_3.png` | Replace with "Paper trade" / "Coming soon"; or hide control until wired |
| 8 | High | 36 px H1 consumes entire above-the-fold on mobile | `iphone13_landing_annotated.png` A1, `pixel7_overflow_annotated.png` E2 | `clamp(20px, 4vw, 36px)`; drop subtitle or move below metric strip |
| 9 | High | "Loading live market data…" banner persists at first paint across all viewports | `desktop_landing.png`, `iphone13_landing.png`, `pixel7_landing.png` | Hide once data present; show only if `fetchedAt > 60s` stale |
| 10 | High | Contrast failures: chip 2.15:1; Sign-in CTA 1.81:1 (manual `#ffffff` on `#22d3ee` = 1.81) | Manual hex calc | Chip text = white; CTA = outline + dark text, or solid `cyan-900` base |
| 11 | High | Pixel 7 metric row clips mid-word ("…WTI $92.96 sp…") | `pixel7_overflow_annotated.png` E1 | Responsive grid: 2-up / 4-up breakpoints |
| 12 | Med | 6 × 16 × 16 help-tooltip icons in sidebar | `iphone13_sidebar_open_fixed.png`; DOM low-res | Inline help under label, or 24 × 24 icon with 20 px halo |
| 13 | Med | 10 unique font sizes on one page | `_dom_desktop.json` `font_sizes` histogram | Consolidate to 12/14/16/20/36; eliminate fractional rem sub-sizes |
| 14 | Med | `keyboard_double_arrow_left` literal text flashes on Material-icon elements | `_dom_iphone13.json` tap-target labels | `<link rel=preload>` the icon font, or swap for inline SVGs |
| 15 | Med | No freshness timestamp above the fold; only buried in chart caption | `desktop_scrollA_2.png` caption at y ≈ 1850 | Add "As of HH:MM UTC · 15-min delayed" under H1 or in ticker row |

## What's right, keep it

1. **Empty-state copy + illustration** on "No actionable trade idea
   today" (`desktop_invD_1.png`) — tone, proportion, and icon all
   land; nothing reads as placeholder.
2. **Confidence bar + `horizon 28 days` + driver bullets** inside the
   verdict card (`iphone13_invD_1.png`, `desktop_scrollA_1.png`).
   Right mental model for a discretionary-trader audience — it just
   needs promoting to be the actual hero.
3. **Brent-vs-WTI price chart** with dual axes, usable date selector,
   clean legend (`desktop_scrollA_2.png`).
4. **Backtest-style "Recent observations" table** under the chart
   (`desktop_scrollA_3.png`) — 16 obs, 100 % hit rate, 28.4-day
   average hold, $3,660 avg winner. The kind of proof-work a trader
   wants, presented without dressing it up.
5. **Natural-language `Drivers:` explainer** at the bottom of the
   verdict card — concise, cites Z-score / cointegration / inventory
   by name. Don't let anyone remove it.

---

*Scoring summary*: comprehension 4 · hierarchy 3 · mobile 3 · desktop
6 · visual 5 · chart 6 · cognitive load 4 · trust 4 · states 5.
Median **4**. A product with a correct thesis and an unfinished
surface. The 30 s test fails because the hero doesn't lead with the
answer; mobile fails because the primary navigation is a 28 px target
at the top of a 36 px headline. Fixes are mostly promotion / demotion
and copy — the underlying data shelf is sound.
