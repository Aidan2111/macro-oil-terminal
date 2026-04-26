# 12 — UX researcher review v2 (Macro Oil Terminal, React stack)

> Reviewer persona: same senior product designer / UX researcher as
> persona 11, hired again to cold-eye the new React stack. Lands on
> `https://delightful-pebble-00d8eb30f.7.azurestaticapps.net/` cold,
> never logs in, pretends to be a Brent/WTI quant trader at 06:50 UTC
> with one coffee in.

---

## Methodology

Captured 2026-04-25 against the live Azure Static Web App. Five routes
(`/`, `/macro/`, `/fleet/`, `/positions/`, `/track-record/`) × three
viewports (desktop 1440×900, tablet 768×1024, iPhone 13 390×844) = 30
baseline shots, plus 17 task-flow shots and 30 dimension-tagged
copies. **Total: 77 PNGs** under
`docs/reviews/ux-evidence-v2/`.

DOM diagnostics (font sizes, sub-44px tap targets, `body.scrollWidth >
innerWidth`, headings, raw body text) captured per viewport into
`docs/reviews/ux-evidence-v2/baseline/findings.json`.

The hero on `/` calls a streaming `POST /api/thesis/generate`. On a
fully cold load the card briefly shows a developer-flavoured empty
state (see `states/`), then settles into the populated trade card
~5–8 s later. Both states are evidenced.

Persona 11 (Streamlit) was read **after** I formed my own scores. A
divergence section closes the doc.

---

## Score card

| # | Dimension                           | Score |
|---|-------------------------------------|------:|
| 1 | First-paint comprehension           |   6   |
| 2 | Plain-English copy                  |   7   |
| 3 | Information density                 |   7   |
| 4 | Visual hierarchy                    |   7   |
| 5 | Trust signals                       |   8   |
| 6 | Live-data legibility                |   7   |
| 7 | Interaction affordance              |   6   |
| 8 | Error / empty / loading states      |   5   |
| 9 | Mobile behaviour                    |   8   |
|10 | Memorability + delight              |   8   |

**Median: 7/10. Mean: 6.9.** Honest read: the React rewrite is a
genuine product, not a toy, and substantially closer to a desk tool
than the Streamlit predecessor. It does **not** clear the 8/10 median
bar — three dimensions (first-paint, affordance, states) drag it down,
and a fourth (live-data) is held at 7 by a single y-axis bug that
torpedoes the most important chart on the most important secondary
route.

---

## 1. First-paint comprehension — **6/10**

**Question**: in 3 seconds, can a quant trader grok stance + market
state?

Cold load on desktop (`first-paint/desktop_home_3s.png`): the eye
lands first on the **scrolling marquee ticker** at the top — Brent
$105.33 (+0.25%), WTI $94.40 (–1.51%), BZ-CL Spread $10.93 (+18.55%),
USCRUDE Inventory 466 Mbbl (+0.42%). Real numbers, real units, four
across, sparkline tails. That's a B+ first hit.

Then the eye drops to the hero card: an outlined `STAND ASIDE` pill
in amber, then the headline "The Brent-WTI spread is slightly
stretched but not enough to act; wait for stronger signals." A trader
gets stance + reasoning in the next two saccades. That's an A.

Why only 6?

- **Cold-cold load shows a developer string**:
  `states/track_record_empty.png` and the raw home empty state
  (`baseline/desktop_home_full.png` first capture, replaced in second
  pass after streaming finished) literally said *"No trade thesis
  generated yet. Kick off the stream via POST /api/thesis/generate."*
  That copy ships to a real user any time the SSE backend is cold —
  a Wave 2 demo will hit this. Treats the trader like a backend dev.
- **Section header on home is `Today's dislocation`**, then a
  subtitle *"Live trade idea, stance, and executable tiers."* The
  word "executable" implies clickable order tiers; nothing on the
  card is actually executable yet (the Pre-Trade Checklist is
  diagnostic, not order-entry). The section header overpromises.
- **No "as of HH:MM UTC" stamp above the fold.** The footer has
  `2026-04-26T02:09:48Z · canadaeast` but it's 870 px below the hero
  on desktop and behind a scroll on mobile.

Evidence: `first-paint/desktop_home_3s.png`,
`first-paint/iphone13_home_3s.png`, `first-paint/desktop_macro_3s.png`,
`states/track_record_empty.png`.

## 2. Plain-English copy — **7/10**

The hero thesis copy is excellent for the audience. Verbatim from the
populated card: *"The Brent-WTI spread is slightly stretched but not
enough to act; wait for stronger signals. The Brent-WTI spread is
moderately stretched at a Z-score of 1.32, suggesting limited
immediate trading opportunities unless further deviation occurs."*

- "Stretched", "Z-score", "stand aside", "no scheduled catalyst",
  "stop at ±2σ", "spread realised vol below the 1y 85th percentile",
  "implied half-life is ~N days" — that is exactly the vocabulary a
  Brent/WTI relative-value desk uses. **Persona 11's complaint about
  jargon is largely fixed.**
- The Pre-Trade Checklist is the strongest copy on the site. Five
  unchecked items, each a sentence in trader vocabulary
  (`copy/hero_copy_mobile.png`).

Why not higher?

- **"Stand aside" is the right idea but the wrong phrasing for a
  trader.** A discretionary book talks about "no edge," "sit out,"
  "flat," "skip." Stand aside reads like a poker tutorial. Minor.
- **Positions page typo**: *"Live paper-trading account. **Closes
  fire** a market order in the opposite direction."* (`copy/positions_typo.png`).
  Should be "Closing **fires**" or "A close fires…". Visible on
  desktop, tablet and mobile — three viewports, one typo.
- **"No EIA release within the next 24 hours."** Trader phrasing is
  "next EIA: Wed 14:30 ET" with the actual scheduled time, not the
  inverted absence-of-release.
- The home subtitle "executable tiers" is a stretch (see #1).
- "Backtest outcomes, hit rate, Sharpe, drawdown" is the Track Record
  subtitle and reads like a column header list. Could say "How the
  model has performed."

Evidence: `copy/hero_copy_desktop.png`, `copy/hero_copy_mobile.png`,
`copy/positions_typo.png`.

## 3. Information density — **7/10**

Desktop home is, if anything, **too sparse** above the fold. The 1440
viewport gives ~1100px to the right of the 240px sidebar; the hero
card occupies that whole width but only ~440px of vertical, then
white space, then a `Market ticker` section that is still a
LoadingSkeleton placeholder (`density/home_desktop.png`). Real
estate is wasted.

Macro page (`density/macro_3up_desktop.png`) is well-tuned: three
stacked sections (Brent-WTI spread chart → Spread stretch Z-chart →
Thesis backtest with 5 KPI tiles + equity curve), each separated by
generous whitespace, none crowded. Bloomberg-density without
Bloomberg cognitive load.

Mobile macro (`density/macro_mobile.png`) compresses the same three
sections into a vertical stream that is genuinely thumb-readable.
Scroll length is ~3,200 px (vs persona 11's 6,003 px on the Streamlit
home — that fixed itself).

Why not 8?

- Home above-the-fold could absorb a small price-move sparkline (last
  N days of the spread) without losing breathing room. Right now it's
  pure copy with a confidence bar.
- Fleet desktop is the inverse: a giant globe that fills the
  viewport with three controls (4 chips) and **no vessel table
  visible** anywhere in the scroll (`density/`/fleet shots).
  Information density of the fleet route is approximately zero.

## 4. Visual hierarchy — **7/10**

On the populated hero (`hierarchy/desktop_home_eyepath.png`), eye
order is correct:

1. Ticker tape (movement attracts).
2. STAND ASIDE pill (outlined amber on dark — high chroma, top-left
   of the hero card).
3. 32-px headline thesis sentence.
4. Smaller body explanation.
5. Confidence bar (amber, animated fill) + horizon.
6. Pre-Trade Checklist with empty radio buttons.

That's the right order for a "should I trade?" product.

Macro page (`hierarchy/desktop_macro_3sections.png`) uses a clean
section pattern: 24-px h2 + grey subtitle + chart. Three sections,
identical visual rhythm. Eye knows where to land.

Why not 8?

- **There is no `<h1>` anywhere in the app** (DOM scan, all viewports).
  All section labels are h2 at 24px. The "Macro Oil Terminal" wordmark
  in the sidebar is a 16px text label, not an h1. Accessibility/SEO
  hit; also a hierarchy hit because nothing earns "page title" rank.
- The fleet page h2 "Vessel" renders at **14px** (per DOM scan) — a
  table column header masquerading as a section heading. Same hierarchy
  level as the rest, half the size.
- Loading skeletons on the home page's "Market ticker" section
  (`density/home_desktop.png`) sit at the same vertical weight as a
  real component would and there is no visual cue they are
  placeholders other than the rounded grey bars themselves.

## 5. Trust signals — **8/10**

This is the most improved dimension over the Streamlit. The page
**looks and reads like a research desk**, not a Streamlit prototype.

- **No dev artefacts in the chrome.** Persona 11 flagged the visible
  Streamlit `Stop` button, `HERO ·` layout-tag copy, and the
  `keyboard_double_arrow_left` ligature flicker. All three are gone.
- **Footer carries `vcfe6aa1 · 2026-04-26T02:09:48Z · canadaeast`**
  on every route — git SHA, server timestamp, Azure region. That is a
  credibility move. Buried (footer-only) but present
  (`trust/disclaimer_research_only.png`).
- **`Research only. Not investment advice. Markets carry risk.`**
  disclaimer in the footer on every route, in muted grey at consistent
  size. Fine.
- **Backtest metrics on `/macro/`** — Sharpe 3.71, Sortino 44.53,
  Calmar 19.46, Hit rate 89.3%, Max DD $-4,302 — labelled clearly,
  with an equity-curve chart underneath
  (`trust/backtest_metrics.png`). That is exactly the proof-work a
  discretionary trader scans for.
- **`Paper account` chip** in amber on the Positions page
  (`trust/paper_account.png`) — sets expectations that this is not a
  live broker. Clear.

What stops a 9?

- **A Sharpe of 3.71 with a hit rate of 89.3% is a "this looks
  in-sample" red flag** for any experienced quant. The page does not
  state lookback period, sample size, or whether it's walk-forward.
  The subtitle says "Mean-reversion trade on the live spread, 1y
  lookback" — 1y is too short for a Sharpe claim and the trader will
  immediately wonder. Trust dings on second glance.
- **"Closes fire a market order"** (Positions copy bug) reads as
  half-shipped — the kind of small typo that makes a quant question
  the rest. Two-letter fix.
- The cold-cold home page literally telling a user to `POST
  /api/thesis/generate` is anti-trust and a P0 to wire to a real
  loading spinner.

## 6. Live-data legibility — **7/10**

The ticker tape has the right anatomy: monospace symbol code (`BZ`,
`CL`, `BZ-CL`, `USCRUDE`), proper-case label (`Brent`, `WTI`,
`Spread`, `Inventory`), value with `$` prefix, signed delta in red
or green, percent in parens, sparkline tail. On mobile the four
cards stack vertically and read perfectly
(`live-data/ticker_mobile.png`).

Brent 105.33 and the briefing example match. Cushing inventory shows
"466 Mbbl" with a +1925 weekly change (units are Mbbl which is
thousands of barrels — fine, conventional). Spread 10.93 shows
+18.55%.

Three real issues:

- **Desktop ticker is a horizontal marquee that clips its leading
  card.** `live-data/ticker_marquee_clip.png` shows the leftmost
  ticker card with the symbol code (`BZ Brent`) hidden behind the
  240-px sidebar — only `$105.33 (+0.25%)` is visible. A trader
  glancing at the top-left sees a price with no symbol.
- **USCRUDE Inventory cell wraps awkwardly on mobile**: the value
  "466" sits stacked above "Mbbl" because the column is too narrow
  (`live-data/ticker_mobile.png`). Reads as two numbers stacked —
  cognitively, "466 / Mbbl" looks like a fraction.
- **Spread stretch y-axis on `/macro/` shows `946671`** as the top
  tick mark instead of e.g. "+2σ" or "+3" (`states/zaxis_garbage.png`,
  `density/macro_mobile.png`). On mobile that bug is on screen at the
  same time the bottom nav is — first thing the eye finds. Almost
  certainly a `toLocaleString` on a sigma value treated as a count, or
  a misnamed scale extent. Single-digit-line fix that singlehandedly
  caps this dimension at 7.

## 7. Interaction affordance — **6/10**

What's clickable, what's status, what's CTA?

Clear:
- Sidebar nav (desktop) / bottom tab bar (mobile): underline + cyan
  active state. Conventional. Hit targets ≥44×44 (DOM scan: 0
  sub-44 tap targets across 15 viewport×route combos).
- Pre-Trade Checklist radios are unmistakeably interactive
  (`affordance/checklist_radios.png`).
- Fleet chips at top of Fleet page (`affordance/fleet_chips.png`):
  pill buttons with a colour dot + count. Look toggleable.

Unclear:
- **The `STAND ASIDE` pill looks clickable** — outlined,
  rounded-full, all-caps — but on hover is a static label
  (`affordance/stand_aside_pill.png`). A trader would expect
  click-to-flip to historical view, or click-to-explain.
- **The Pre-Trade Checklist radios are checkable** but checking them
  appears to do nothing (no persisted state, no "ready to trade"
  unlock). Affordance promises an interaction it doesn't deliver.
- **No "execute paper trade" or order-tier CTA on the hero** despite
  the subtitle promising "executable tiers". Empty Positions page
  helpfully says *"Place a trade from any Trade Idea"* but no Trade
  Idea has a place-trade button.
- **Globe on Fleet page** is rotatable / draggable but there's no
  affordance hinting at this — no "drag to rotate" tooltip, no
  cursor-grab on hover.

## 8. Error / empty / loading states — **5/10**

Mixed bag.

Good:
- **Track Record empty state** (`states/track_record_empty.png`):
  scatter-plot icon, headline "No thesis history yet", body "Once the
  model has generated theses with outcomes, they show up here." —
  on-brand, doesn't read as broken.
- **Positions empty** (`states/positions_empty.png`): cylinder icon,
  "No open paper positions.", subtext "Place a trade from any Trade
  Idea." Good copy, useful next-step nudge.
- **Loading skeletons** on Market ticker section: rounded grey bars,
  no spinner, no text. Doesn't shout "broken."

Bad:
- **Cold thesis empty state** literally tells the user to *"Kick off
  the stream via POST /api/thesis/generate."* This is a
  developer-facing instruction shipped to a trader. Should be a "We
  haven't generated today's read yet — refresh in a moment" or an
  auto-poll. P0.
- **Spread-stretch y-axis label `946671`** (`states/zaxis_garbage.png`)
  is an error state masquerading as data. The chart paints; the axis
  is wrong; nothing tells the user the axis is wrong.
- **Empty Trade Idea has no retry / refresh affordance**. If the
  stream fails or hasn't kicked off, the user has no way to recover
  without page refresh.
- **No error state observed** for genuine failures (timeouts, 500s)
  — couldn't trigger one in this audit, but the cold-empty proves
  the framework is "leak the dev string."

## 9. Mobile behaviour — **8/10**

This is the biggest delta from persona 11 (he scored Streamlit mobile
at 3/10). DOM scan on iPhone 13:

- **Zero horizontal scroll** on all five routes (vs Streamlit's
  Pixel-7 mid-word clipping).
- **Zero sub-44×44 tap targets** on all five routes (vs Streamlit's
  31 tap targets on iPhone 13 landing alone, including a 28×28
  sidebar chevron that was the only path to controls).
- **Bottom tab bar**, conventional 5-icon pattern, all 44+ targets,
  active state in cyan (`mobile/bottom_nav.png`). Thumb-zone perfect.
- **Ticker stacks vertically** as four cards above the hero, each
  card 60+ px tall (`mobile/home_thumb.png`). One-thumb scrollable.
- **Hero card is the entire above-the-fold content** below the ticker
  — STAND ASIDE pill, headline, body, confidence, horizon all visible
  before any scroll (`mobile/home_thumb.png`). A trader can answer
  "what's the read?" without scrolling. That is the dimension.

Why not 9 or 10?

- **Spread-stretch chart on `/macro/` has the bottom nav overlapping
  its top axis label** at 390×844 (`mobile/macro_full_with_navbar.png`).
  The `946671` label is right next to the navbar's "Macro" tab icon.
- **Fleet globe is sized larger than the viewport on mobile**
  (`mobile/fleet_globe_clipped.png`) — the bottom 30% of the globe is
  hidden behind the bottom nav. Aesthetically it looks ok (bottom-fade
  globe), functionally Antarctic / South Atlantic vessels would never
  be tappable.
- **No iPad-specific layout** — at 768×1024 the desktop sidebar still
  shows; that is fine but the page spends 240px of 768px on nav.

## 10. Memorability + delight — **8/10**

The product has a **distinctive aesthetic**: deep navy `#0b0f14`
ground, cyan `#22d3ee` and amber `#f59e0b` as the only chroma
families, monospace symbol codes (BZ, CL, BZ-CL, USCRUDE), Alvar
Aalto-style generous whitespace.

Memorable elements:
- The **night-side Earth globe** on `/fleet/` is genuinely cinematic
  (`delight/desktop_globe.png`). Even with no vessels rendered yet, a
  trader who lands on this page once will remember it.
- **STAND ASIDE in amber** on the hero is a strong, repeatable
  visual identity. Compare to a Bloomberg "FLAT" cell — same idea,
  prettier (`delight/mobile_hero_pill.png`).
- **The three-chart Macro stack** (spread → stretch → backtest) is
  a coherent narrative: "here's the spread, here's how stretched it
  is, here's how the model would have done." Memorable as a story
  shape (`delight/macro_three_charts.png`).

Why not 9?

- **The globe is wasted real estate** until vessels render. Promise
  unfulfilled = anti-delight on second visit.
- **No micro-interactions** (no hover-grow on chips, no tooltip on
  charts, no animated transition between routes). Charts are static.

---

## Top 5 things to fix this week

1. **`components/hero/TradeIdeaHero.tsx` (or wherever the empty state
   lives) — replace `"No trade thesis generated yet. Kick off the
   stream via POST /api/thesis/generate."` with a real loading state.**
   Either auto-trigger the generate stream on mount, or show a
   spinner + "Generating today's read…" until SSE returns. Currently
   shipping a dev instruction to traders. P0 trust killer. Evidence:
   `states/` (the original cold-cold capture). One file, ~10 lines.

2. **`components/charts/SpreadStretchChart.tsx` (or whichever file
   draws the Z-score chart on `/macro/`) — the y-axis top tick reads
   `946671` instead of `+2σ` or `+3`.** Likely a `toLocaleString` on
   a sigma value or wrong domain extent. Half-day fix, single-digit
   trust impact, biggest single visual hit on the most-trusted page.
   Evidence: `states/zaxis_garbage.png`, `density/macro_mobile.png`.

3. **`components/positions/PositionsHeader.tsx` (or src
   equivalent) — `"Closes fire a market order"` → `"Closing fires a
   market order"`.** Two-character typo visible on three viewports.
   Pure trust hit. Evidence: `copy/positions_typo.png`.

4. **`components/ticker/TickerTape.tsx` — the marquee leading-edge
   clipping plus the mobile "466 / Mbbl" wrap.** Either lock the
   leading card to the viewport edge (no clip), or pad the marquee
   container so the first symbol is always whole. For mobile, set
   the `<value> <unit>` pair to flex-row with `flex-nowrap` so the
   "466 Mbbl" reads as a single unit. Evidence:
   `live-data/ticker_marquee_clip.png`, `live-data/ticker_mobile.png`.

5. **`components/hero/StancePill.tsx` — copy + behaviour.** Replace
   `STAND ASIDE` with `NO EDGE` or `SIT OUT` (trader vocabulary), and
   either make the pill click-to-show-history (the obvious affordance
   it currently fakes) or remove the outline + caps treatment so it
   reads as a status badge, not a button. Evidence:
   `affordance/stand_aside_pill.png`. While there, also drop the home
   subtitle "executable tiers" until tiers are actually executable —
   it sets up an expectation the page never delivers.

Honourable mentions (if there's a sixth slot): add an `<h1>` on every
route (currently zero h1s in the entire app — accessibility fail),
add a `walk-forward` / `out-of-sample` qualifier under the Sharpe
3.71 number on `/macro/`, and add an "as of HH:MM UTC" stamp into
the ticker row (currently footer-only).

---

## vs persona 11 (Streamlit reviewer)

Persona 11 reviewed the now-retired Streamlit app and scored a
median **4/10** with comprehension 4, hierarchy 3, mobile 3, desktop
6, visual 5, chart 6, cognitive load 4, trust 4, states 5. My v2
median is **7/10**. Five concrete divergences:

1. **Mobile usability is no longer a disaster.** Persona 11 cited 31
   sub-44×44 tap targets on iPhone 13 and a 28×28 sidebar chevron as
   the sole control gateway. The React app has **zero** sub-44 tap
   targets across 15 viewport×route combos and a conventional bottom
   tab bar. I scored mobile 8 vs his 3 — a 5-point swing on the
   single biggest finding in his review.

2. **The Bloomberg-cognitive-load problem inverted.** He counted 22+
   distinct first-paint elements with no progressive disclosure; I
   count ~10 (ticker × 4 cards + hero pill + headline + body + bar +
   horizon). The new home is, if anything, slightly *too* sparse on
   desktop. Density 7 vs his cognitive-load 4.

3. **Trust artefacts cleaned up.** He flagged the visible Streamlit
   `Stop` button, `HERO ·` layout-tag copy, `keyboard_double_arrow_left`
   ligature flicker, and `execute — wiring` placeholders. None of these
   are present in the React build. I scored trust 8 vs his 4.

4. **The new product introduced a new dev-string leak.** The cold
   home empty state telling the user to `POST /api/thesis/generate`
   is the same *kind* of mistake persona 11 saw on Streamlit
   (developer-facing copy escaping to prod), just from a different
   layer of the stack. Worth flagging that the team has the bug
   pattern, not just the bug.

5. **Persona 11 was right about the chart bones, and the React team
   kept them.** His most positive call-out was the Brent-vs-WTI
   chart with dual axes and a clean legend, plus the Z-score plot
   under it. The React `/macro/` page kept that exact shape and
   added a backtest equity curve underneath. Continuity of the right
   calls is worth crediting; the y-axis bug on the Z-chart is the
   one regression in this set.

---

## Final score

**Median: 7/10.** Below the 8/10 target.

Dimensions that dragged it down:
- **First-paint comprehension (6)** — cold dev-string empty state +
  no above-the-fold "as of" stamp.
- **Interaction affordance (6)** — STAND ASIDE looks clickable, isn't;
  Pre-Trade Checklist radios look stateful, aren't; "executable
  tiers" promised, not delivered.
- **Error / empty / loading states (5)** — the dev-string leak plus
  the malformed Z-axis are both error states the user can hit on
  ordinary navigation.

Three of the ten dims are at 6 or below; the other seven are at 7 or
8. **Fix the cold empty state, fix the Z-axis label, fix the typo,
fix the marquee clip, and rewrite the STAND ASIDE pill** — and the
median lifts from 7 to 8 without touching the other dimensions. The
underlying product is real research, not a toy. The surface is one
sprint of polish away from earning the desk.

*Scoring summary*: 1·6 · 2·7 · 3·7 · 4·7 · 5·8 · 6·7 · 7·6 · 8·5 ·
9·8 · 10·8. Median **7**.
