# UI polish pass — Brainstorm

> **Status:** RESOLVED + AMENDED (2026-04-22 01:05Z).
> Ten visual-polish sections from the original brief, plus two
> corrections baked in at 01:05Z:
> - **Generic branding.** No "Aidan's Desk" / personalization. Product
>   is "Macro Oil Terminal" throughout.
> - **Deeper plain-language pass.** Not just "dislocation → spread
>   stretch" but a full rename table + qualitative labels on every
>   numeric metric + a new `plain_english_headline` field on the LLM
>   thesis output. Tooltips preserve the technical terminology for
>   anyone who wants the math.
>
> The corrections introduce a new upstream task **UIP-T0** (language
> pass) that every downstream visual task depends on — the hero tiles,
> charts, checklist etc. all consume the renamed constants. See design
> spec (`docs/designs/ui-polish.md`) and plan (`docs/plans/ui-polish.md`).

## The user problem, restated

The product is **Macro Oil Terminal** — a generic, reusable research
terminal for oil-spread dislocations. Primary user for now is the
creator and a handful of friends; the UI must read generic, not
personal. The hero Trade Idea band + the three tabs are functionally
correct but look like a dev dashboard, not a Bloomberg-grade terminal.
We want the demo looking sharp before Alpaca trade buttons land in the
instrument tiles — the buttons should feel like pressing an "execute"
key on a terminal, not clicking a default Streamlit button. The
target audience for copy is **a smart generalist with no finance
background**: think "trader's buddy explaining over beers," not
textbook, not Wall Street.

## Why now

Two reasons:

1. Alpaca is days away. If we ship execute buttons into a surface that
   looks unpolished, the "can I trust clicking this?" trust signal is
   weak. Polish first = execute feels inevitable.
2. Polish is high-variance work. Doing it *in* the same PR as Alpaca
   mixes cosmetic iteration (lots of trial + error, screenshots,
   subjective) with financially-sensitive logic (order placement). Mix
   them, and the PR is unreviewable. Keep polish its own branch,
   land, then put Alpaca into a fixed visual surface.

## Alternatives considered

### A. Keep the current tab shape, polish in place

Minimal risk, each section of the brief is a small change inside the
existing layout. **Chosen baseline.**

### B. Replace tabs with a single-scroll page + sticky left nav

The brief lists this as "Option B" for section 5. It would be a bigger
refactor — named sections (Macro / Depletion / Fleet / Model
internals) linked from a sticky nav. The hero stays as a persistent
top band. **Decision:** Defer to a follow-on branch. The brief
explicitly asks us to decide during design review; we choose to keep
the tab layout for this polish pass because:

- Tab layout works on mobile via scroll.
- Our existing e2e test suite targets tab locators; a single-scroll
  refactor would churn ~6 tests.
- The polish the brief describes (theme, palette, hero, ticker, chart
  styling) is orthogonal to layout. We can evaluate layout after the
  polish lands and see whether tabs still feel redundant.

Logged in the plan as **"P2 layout review"** — reopen once the visual
language is in place and we can judge whether tabs-vs-single-scroll
reads better with the new aesthetic.

### C. Rip + replace with a real design system (MUI, Mantine via React)

Would require exiting Streamlit. Out of scope for this pass.

## Theme palette — proposed defaults

Aidan's brief suggests: deep navy bg, electric cyan primary, warm
amber warnings, crimson alerts, muted sage positives. Concrete hex
picks:

| Token | Hex | Usage |
|---|---|---|
| `bg_1` (deepest) | `#0A0E1A` | App background |
| `bg_2` | `#121826` | Card background |
| `bg_3` | `#1B2232` | Hover / elevated |
| `border` | `#2A3245` | Hairline borders |
| `text_primary` | `#E6EBF5` | Headings, metrics |
| `text_secondary` | `#9AA4B8` | Captions, axis labels |
| `text_muted` | `#5B6578` | Footer, disclaimer |
| `primary` | `#22D3EE` (cyan-400) | CTA, active tab, active brand |
| `primary_glow` | `rgba(34, 211, 238, 0.35)` | Stance-pill glow, focus rings |
| `warn` | `#F59E0B` | Warnings, amber indicators |
| `alert` | `#EF4444` | Z-score breach, errors |
| `positive` | `#84CC16` (sage) | Green delta, long stance |
| `negative` | `#F43F5E` | Red delta, short stance |
| `gridline` | `rgba(255,255,255,0.06)` | Chart gridlines |

Stance colouring maps: `LONG SPREAD → positive`, `SHORT SPREAD →
negative`, `STAND ASIDE → text_secondary`.

## Iconography

**Choice: Lucide via CDN**, loaded once in the injected CSS block as
inline SVG sprites. Reasons:

- Lucide is widely used, stable, CC-BY.
- CDN (`https://unpkg.com/lucide-static@latest/icons/`) avoids a pip
  dep.
- Exactly one icon family — no Phosphor + Lucide + emoji mix.
- For the oil-barrel logo, we custom-draw a small SVG (a couple of
  dozen path points). Keeps vendor lock-in to zero.

## Typography

- Heading stack: `'Source Sans Pro', -apple-system, 'Segoe UI', sans-serif`
  (same as Streamlit default; don't fight the framework).
- h1 36/700, h2 24/600, h3 18/600, body 14/400, caption 12/400 muted.
- Monospace for prices and metrics: `'JetBrains Mono', ui-monospace,
  SFMono-Regular, monospace` (terminal feel).

## CSS injection strategy

- **Single `st.markdown("<style>…</style>", unsafe_allow_html=True)`**
  call at the top of `app.py`, wrapped in
  `if "css_injected" not in st.session_state:` so it only fires once
  per session.
- Source of the CSS lives in `theme.py::inject_css()` → a module-level
  constant, easy to diff.
- Media queries live in the same block; no external stylesheet (avoids
  FOUC and keeps everything in-repo).

## Loading / empty / error states

- **Loading:** wrap every `@st.cache_data`-fronted fetch call in
  `with st.status("Fetching live prices…", expanded=False):` — this is
  a native Streamlit primitive added in 1.28+. Already available.
- **Empty states:** single SVG illustrations (we draw) + one-line copy.
  Centralise under `theme.py::render_empty(icon, message)`.
- **Error states:** `theme.py::render_error(message, retry_fn)` →
  Renders `st.error(message)` + a `st.button("Retry now", ...)`.
  Swallow raw exceptions upstream in every `data_ingestion.py` /
  `providers/*.py` public function.

## Performance budget

- Current warm TTI: ~1.0s. Target: < 2.0s warm, < 4.0s cold.
- Injecting CSS via `st.markdown` is cheap (inline, no extra request).
- Playwright TTI measurement: `performance.timing.domContentLoadedEventEnd - navigationStart`.
- Playwright first-paint: `performance.getEntriesByType("paint")[0].startTime`.
- Before-after deltas logged in `docs/perf/ui_polish_deltas.md`.

## Open questions

None — Aidan's brief is complete. Palette + icon family picked under
conservative defaults; Option B layout deferred to P2 with rationale;
all 10 scope sections map 1:1 to plan tasks T1–T10.

## Residual default

For anything that surfaces mid-work and isn't covered: most-
conservative, minimal, reversible. Record the call in PROGRESS.md
and keep moving.

---

## Corrections (2026-04-22 01:05Z)

### Branding

Everything says **"Macro Oil Terminal"**. No "Aidan", no "Aidan's Desk",
no personalized greetings. Target user is a smart generalist with no
finance background — product reads generic, not a personal tool.

Surfaces to strip:
- Page title, favicon tooltip: `Macro Oil Terminal`.
- Footer: disclaimer + build version + deployed region only. No name.
- README header: no personal pronouns.
- No "welcome Aidan" / greeting copy anywhere.

### Plain-language terminology

The audience is "smart generalists, no finance background". Every
finance-flavored term gets a plain-English replacement as the default
UI surface. Technical terms move into tooltips (`help=`) for anyone who
wants the math. Rename table lives in the design spec.

**Principle:** the number stays, the label carries the meaning.
`Stretch: 2.4 (Very Stretched)` — someone who reads only the word
"Very Stretched" understands what's going on.

Qualitative bands (defaults):

| Metric | Band cutoffs |
|---|---|
| Stretch | < 0.7 "Calm" · 0.7–1.3 "Normal" · 1.3–2.3 "Stretched" · 2.3–3.2 "Very Stretched" · ≥ 3.2 "Extreme" |
| Confidence (1–10) | 1–3 "Low" · 4–6 "Medium" · 7–8 "High" · 9–10 "Very High" |
| Correlation | 0–0.3 "Weak" · 0.3–0.6 "Moderate" · ≥ 0.6 "Strong" |

### Plain-English headline on the trade idea

New field on the LLM output JSON: `plain_english_headline` — one
sentence, anyone-understands, no jargon. Example:

> *"Brent is trading unusually expensive vs WTI right now. This kind
>  of gap usually closes within 3 weeks, so it's a good moment to bet
>  on the gap narrowing."*

Renders as the top line of the trade-idea card, above the stance pill.

### Tooltip contract

Every renamed metric's `help=` keeps the technical name. Example:

> **Spread Stretch: 2.4 (Very Stretched)**
> *Also called Z-score or dislocation. This measures how far today's
>  spread is from its normal range, expressed as multiples of the usual
>  daily move. 2.4 means the spread is 2.4× its usual wobble above
>  average — statistically unusual.*

Tooltips are the one place the old terminology survives.

### Acceptance bar

Aidan's litmus test: *"Screenshot a non-finance friend would understand
without explanation."* The finishing-flow screenshots are the
verification — if a reviewer can't follow the UI without a glossary,
T0 didn't land.
