# 09 — Behavioural-UX / Cognitive-bias review (Phase A)

**Reviewer lens:** behavioural-UX researcher. I read the hero band, the
stance pill, the conviction bar, the "key drivers" list, the stop display,
and the disclaimer strip as a *decision environment* — the question is not
"does it look nice" but "what decision will a tired retail user make at
11pm after two beers?". The product copy explicitly targets "a smart
generalist with no finance background" (`docs/brainstorms/ui-polish.md:29-31`),
so I hold the UI to that standard: every pixel either helps that user
stay calibrated, or it leans them toward a trade they'd regret.

Findings are severity-ranked. Severity reflects *expected behavioural harm*
(how likely the bias is to trigger a real money loss), not visual polish.

---

## S1 · CRITICAL — The `plain_english_headline` field is generated but never rendered

The schema defines a required `plain_english_headline` string
(`trade_thesis.py:193-200`, `:202-208`), the prompt asks the model to write
one first (`trade_thesis.py:220-225`), and the design spec explicitly places
it *above* the stance pill as the hero's top line
(`docs/designs/ui-polish.md:404-418`). A post-validation fallback even
synthesises one when the model returns empty (`trade_thesis.py:924-942`).

It is **never rendered in the UI.** `_render_thesis_mini` shows only
`stance → conviction → horizon → thesis_summary` (`app.py:768-787`). The
`plain_english_headline` attribute on the `Thesis` dataclass
(`trade_thesis.py:272`, `:949`) has zero read sites in `app.py`
(grep confirms — only writes in `trade_thesis.py`).

**Behavioural impact.** The headline was the one element designed to
*hedge* — a calibrated, plain-language framing ("usually closes within 3
weeks, so it's a good moment to bet on the gap narrowing"). Without it,
the hero leads with a **coloured UPPERCASE pill** (`theme.py:410-438`)
that reads `BUY THE SPREAD` or `SELL THE SPREAD`. That is pure imperative.
The nuance-giving layer is present on the backend, fails open, and
silently disappears. This is the single largest overconfidence-induction
defect in the current UI.

**Fix:** render `thesis.plain_english_headline` as the first child inside
`_render_hero_band`, above `_render_thesis_mini`, with
`data-testid="plain-english-headline"` (already specified in
`docs/designs/ui-polish.md:456`).

---

## S2 · CRITICAL — Stance copy ("Buy / Sell / Wait") is prescriptive, not descriptive

`language.TERMS` maps `long_spread → "Buy the spread"`,
`short_spread → "Sell the spread"`, `flat → "Wait"`
(`language.py:60-64`). The pill uppercases those
(`theme.py:426-432`) and renders them at `font-size:14px; font-weight:600;
text-transform:uppercase; letter-spacing:0.5px; min-width:160px`
(`theme.py:101-113`) with a glowing drop-shadow (`box-shadow: 0 0 20px {color}55`
at `theme.py:437`).

For a smart generalist, `BUY THE SPREAD` reads as **instruction**, not
**hypothesis**. Compare to the original schema enum values
(`long_spread`/`short_spread`/`flat` at `trade_thesis.py:136`), or to the
tooltip copy ("Buy Brent and sell WTI in equal-risk proportions —
profit when the Brent-WTI gap widens", `language.py:182-185`), both of
which are descriptive. The rename pass dropped the hypothesis framing.

**Crowding-out of nuance.** With only three copy tokens (Buy / Sell /
Wait), there is nowhere for the model to say "lean long, but half-size,
and only after EIA". The schema *can* express nuance — `conviction_0_to_10`,
`position_sizing.suggested_pct_of_capital`, `invalidation_risks`,
`data_caveats` — but the pill dominates the visual hierarchy and those
fields are either downranked (summary caption, `app.py:786-787`) or
hidden entirely (invalidations — see S3).

**Fix options, cheapest first:**
1. Copy change: `"Buy the spread" → "Lean long"`, `"Sell the spread" →
   "Lean short"`, `"Wait" → "Stand aside"`. (`language.py:61-64,266-276`.)
2. Structural: render a second line under the pill with the model's
   qualifier ("with low confidence", "half-size until EIA"). Uses data
   already in `raw["position_sizing"]["rationale"]`.

---

## S3 · HIGH — `invalidation_risks` and `data_caveats` are generated but never shown in the hero

`trade_thesis.THESIS_JSON_SCHEMA` requires `invalidation_risks` (array,
`trade_thesis.py:172`) and `data_caveats` (array, `trade_thesis.py:186`).
Guardrails append to `data_caveats` when conviction is capped
(`trade_thesis.py:411-414`), when cointegration fails
(`trade_thesis.py:460-464`), or when vol is top-15%
(`trade_thesis.py:442-446`). These are exactly the "slow down" signals a
behavioural UX needs.

`grep data_caveats app.py` and `grep invalidation app.py` return only
internal uses — **neither array is rendered on screen.** The hero
shows `thesis_summary` (a promotional paragraph) and skips the risks.

This is textbook **confirmation bias by omission**: the user sees only
the reasons-to-act ("key drivers" in `thesis_summary`) and none of the
reasons-to-not-act. The system was designed with the antidote
(`invalidations`, `catalysts`, `data_caveats`) and the UI removes it.

**Fix:** render `invalidation_risks[:3]` as a muted caption under the
checklist inside `_render_hero_band` (`app.py:1027-1088`), and surface
`data_caveats` as a dedicated warning strip when non-empty. The
`TERMS["invalidations"] = "What would break this trade idea"` key
(`language.py:56`) already exists — it's imported and never used.

---

## S4 · HIGH — Disclaimer is cognitively invisible

`_HERO_DISCLAIMER` is defined at `app.py:682-687` and rendered *only*
through `st.caption(...)` (`app.py:1024`, `:1088`, `:1147`). Streamlit
`st.caption` styles to `font-size: 12px; color: var(--text-muted)`
(`theme.py:78-79`) — i.e. `#5B6578` (`theme.py:37`), the lowest-contrast
colour in the palette against `bg_1 #0A0E1A`. The footer repeats it as
"Research & education only" (`theme.py:1456`) in the same muted token
(`theme.py:318` — `color: var(--text-muted); font-size: 12px`).

Contrast: the stance pill uses the saturated `positive`/`negative` tokens
with a 20-px coloured glow (`theme.py:437`). The visual weight ratio
between the action prompt and the "this is not advice" disclaimer is
roughly 10:1 in favour of the action prompt.

**Behavioural impact.** Disclaimers that cannot be *seen* cannot *debias*.
Research on mandated-warning salience (Loewenstein et al., boilerplate
language) is consistent: low-salience disclaimers functionally do not
exist. A real-money loss lawsuit would not care that
`app.py:682-687` contains the warning — only whether it was presented
with comparable salience to the recommendation. It is not.

**Fix:** move the leftmost 40 characters of `_HERO_DISCLAIMER` ("Research
& education only. Not personalised advice.") into the **same row** as the
stance pill, at `text-secondary` (#9AA4B8) not `text-muted`, so it sits
adjacent to the action prompt. The full disclaimer stays where it is.

---

## S5 · HIGH — Conviction 0–10 + "Very High" band invites overconfidence

`describe_confidence` maps 9–10 → `"Very High"` (`language.py:239-240`),
and the conviction bar renders a 100% fill at value 10 (pct = `v*10`,
`theme.py:459-460`). The bar's fill colour matches the stance's semantic
direction — green for LONG, red for SHORT (`theme.py:383-396`,
`:461-475`) — so a "Very High" LONG reads as a full-width bright-green
bar with a glowing green pill above it.

Problems, stacked:
1. **Ceiling framing.** "Very High" on a 10-point scale with a 100% bar
   implies the model has exhausted its uncertainty. A calibrated
   confidence is almost never 10/10; the very existence of the band
   tempts the model (and the user) toward it.
2. **Miscalibration vs backtest.** Guardrails already cap conviction at
   5.0 on a weak backtest (`trade_thesis.py:406-414`) and at 5.0 on a
   broken cointegration (`trade_thesis.py:455-459`). That is the right
   shape — but the *band labels* don't reflect it: a 5/10 still reads
   as `"Medium"` (`language.py:237-238`), which sounds neutral rather
   than "capped because the stats don't support more."
3. **Colour-coded toward action.** Both LONG and SHORT get saturated
   conviction-bar colours; only FLAT/STAND_ASIDE gets the muted
   `text_secondary` (`theme.py:395-396`). Action stances are
   visually rewarded.

**Fix:**
- Cap the band label at `"High"` unless backtest Sharpe > 1.5 AND
  cointegration is strong — i.e. gate `"Very High"` on evidence, not a
  number threshold.
- When `guardrails_applied` contains a calibration adjustment, badge the
  conviction bar ("capped — weak backtest") — the info is already in
  `thesis.guardrails_applied` (`trade_thesis.py:951`) and is only
  surfaced in the model-internals expander (`app.py:1693-1694`).

---

## S6 · HIGH — Green/red colour coding biases toward action vs inaction

The stance colour map is explicit: `LONG_SPREAD → PALETTE.positive`
(#84CC16, sage-green, `theme.py:392-393`), `SHORT_SPREAD → PALETTE.negative`
(#F43F5E, rose-red, `theme.py:394-395`), and the fallback for FLAT /
unknown → `PALETTE.primary` (cyan, `theme.py:396`) inside
`_stance_color`. But `render_stance_pill` overrides the FLAT path to
`text_secondary` (grey, `theme.py:431-432`) — so the three visual
treatments read as:

- LONG: bright green, glowing, satiated → **go**.
- SHORT: bright red, glowing, alarming → **act**.
- WAIT: grey, flat, muted → **boring**.

Both directional stances are visually louder than `WAIT`. The desk-style
summary strip at `app.py:581-610` reinforces this — green pill for BUY
SPREAD (`#2ecc71`), red pill for SELL SPREAD (`#e74c3c`), washed-out grey
for WAIT (`#95a5a6`, `app.py:585-586`).

**Behavioural impact.** **Status-quo / inaction bias is normally
protective** — retail traders lose money by trading, not by waiting. The
colour system inverts that: WAIT is punished visually, making the model's
default, safest stance feel like the least attractive option.

**Fix:** give WAIT a colour that reads as *deliberate* rather than
*empty*. Amber `--warn` (#F59E0B, `theme.py:40`) with a subtle ring is a
reasonable alternative — it signals "hold" rather than "dead air."
Alternatively, desaturate the long/short pills so they don't outshine
the wait state.

---

## S7 · MEDIUM — Anchoring on the stance pill's `min-width: 160px`

`.stance-pill { min-width: 160px; text-align: center; }`
(`theme.py:110-112`). The pill always occupies the same pixel footprint
regardless of the model's uncertainty. A 2/10 conviction LONG and a 9/10
conviction LONG render **identically-sized** pills — same glow, same
uppercase weight, same width.

This is a classic **anchoring-on-format**: visual format is a stronger
cue than the numeric band label tucked into the tiny conviction-bar
caption below (`theme.py:462-467`, rendered at `caption` size = 12px).
The pill sets the first impression; the confidence qualifier arrives
second, smaller, and muted.

**Fix:** scale pill opacity or border-width with conviction. At
conviction ≤ 3, render the pill outlined (no fill) with a caption
"low-confidence lean"; at ≥ 7, the current filled treatment is fine.
This costs one ternary in `render_stance_pill` (`theme.py:410-438`).

---

## S8 · MEDIUM — Framing effect: "Stretched" vs "Dislocated" across surfaces

The rename pass (`language.py:31`) standardised the public label on
`"Spread Stretch"`, with `describe_stretch` returning `"Calm" / "Normal"
/ "Stretched" / "Very Stretched" / "Extreme"` (`language.py:200-221`).
That's behaviourally sound — "stretched" implies **elasticity and
eventual return**, which is exactly the mean-reversion thesis.

But the tooltip at `language.py:78-83` says *"Also called **Z-score** or
**dislocation**"*, and the system prompt at `trade_thesis.py:227-230`
instructs the model to *"Prefer terms like 'dislocation' over 'Z-score'
... in your thesis_summary and key_drivers prose."* So the user sees
"Stretched" on the headline metric but reads "dislocated" in the hero's
own summary caption.

"Stretched" primes a reverting mindset. "Dislocated" primes a *broken*
mindset — more emotional, more action-seeking. Mixing both in the same
hero is a framing inconsistency that the user has to resolve silently.

**Fix:** the prompt contract at `trade_thesis.py:227-230` should match
the UI — prefer "stretch" / "stretched" over "dislocation" in prose.

---

## S9 · MEDIUM — Stop display prioritises the Z-level, not the dollar loss

The JSON schema exposes both `stop_z_level` and `stop_loss_condition`
(`trade_thesis.py:155-158`), and the rule-based fallback computes a
`stop_z` at entry ± 2.0σ (`trade_thesis.py:489, :503-504`). The tier cards
render legs and a `size_usd` preview (`theme.py:500-518`) but the stop is
not rendered in the hero at all — it's only reachable through the
"Model internals" expander.

Behaviourally, a stop expressed in **sigma** is abstract; a stop
expressed in **dollars** is concrete. Users anchor on whatever number
the UI hands them. The checklist has *"I have a stop at ±2σ spread
move from entry"* (`trade_thesis.py:310-312`), which is worse: it asks
the user to *affirm* a sigma stop without ever computing the dollar
equivalent for them.

**Fix:** in `_render_tier_tile` (`app.py:800-856`) add a caption
"Stop ≈ $X at -2σ" computed from `size_usd * 0.02`. Concrete dollar
losses are what make stop discipline stick.

---

## S10 · MEDIUM — "Key drivers" list is generated but not rendered; "thesis_summary" is, and it only confirms

The schema requires `key_drivers` (1–6 strings, `trade_thesis.py:171`)
and `thesis_summary` (`trade_thesis.py:170`). The hero shows only
`thesis_summary` (`app.py:772-787`). Semantically, `thesis_summary` is
the "what I think" narrative; `key_drivers` are the "why I think it"
bullets. Showing only the narrative *without* the supporting bullets
encourages confirmation bias — the user nods along with a
well-written paragraph and never sees which of the five drivers they
should disagree with.

Worse: `key_drivers` are typically written as confirmatory ("Spread Z
+2.4σ vs threshold ±3.0σ", `trade_thesis.py:518`) without
counterweights. The schema's countermeasure is `invalidation_risks` —
see S3 — and neither half is rendered.

**Fix:** render `key_drivers` alongside `invalidation_risks` as a
two-column "what supports this / what breaks this" block. The data is
there; it's a view-layer addition only.

---

## S11 · LOW — Onboarding toast leads with a compliment, not a caution

`_ONB_COPY_2` reads `"The hero card is the current trade idea. Confidence
tells you how strong the signal is."` (`theme.py:1147-1150`). For a
first-time user, the very first framing of *confidence* is presented as
a signal-strength meter — no caveat that the model's confidence is not
calibrated to their portfolio, account size, or risk tolerance.

**Fix:** append a hedging clause: *"Confidence is the model's view of
the signal — not a recommendation about size or timing for you."* Still
fits in the 340-px toast width (`theme.py:1160`).

---

## S12 · LOW — The "Very extreme stretch" band and "Extreme" dislocation tooltip may legitimise outlier chasing

`describe_stretch` at `|Z| ≥ 3.2` returns `"Extreme"` (`language.py:221`),
and `TERMS["stretch_extreme"] = "Very extreme stretch"`
(`language.py:33`), with a tooltip that frames it as *"Statistically
rare — the spread is this far from its normal range only a few times per
year on average."* (`language.py:95-98`).

Behaviourally, labelling something "Extreme" in a mean-reversion product
is a **"buy-the-dip" primer**: it tells the user the outlier is a
trading opportunity, without the counterweight that extreme moves are
also when regime change happens (cointegration broken). The guardrail at
`trade_thesis.py:449-464` exists precisely because of this risk, but the
UI label still flags extremes as opportunities.

**Fix:** rename the `≥ 3.2` band to `"Extreme — handle with care"` and
show the `coint_verdict` pill next to it when the latter is `broken` or
`weak`. The data is already wired through the hero context
(`app.py:1117-1118`); only the render is missing.

---

## Summary

Behavioural-UX verdict: the app's backend contract is **more calibrated
than its UI**. The schema has invalidations, data caveats, plain-English
headlines, reasoning summaries, and stop levels; the UI renders only the
action prompt, a green/red confidence bar, and a promotional summary.
Fixing S1-S4 alone (render the headline, soften the stance copy, surface
invalidations + caveats, raise the disclaimer salience) would
materially de-bias the current surface without touching the quant
logic.

The strongest single finding is **S1** — the plain-English headline is
the UI's intended hedging layer and it is currently dead code between
`trade_thesis.py:949` and the user's screen.
