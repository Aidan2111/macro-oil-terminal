# Hero Trade Thesis + Executable Instruments — Brainstorm

> **Status:** DRAFT. Needs user approval before the design spec is finalised.
> The Superpowers `brainstorming` skill has a HARD-GATE — no implementation
> starts until Aidan has signed off on the design that follows from this
> brainstorm.

## The user problem, restated

> *"What do my users do with this information?"*

Today the terminal produces a high-quality Trade Thesis (Azure-OpenAI-generated,
structured JSON, guardrailed, materiality-gated, dual-mode UI). A desk reader
can read it and nod. But they close the tab and nothing has changed in their
world. They don't know:

1. **Is the thesis actionable for me specifically?** (Am I allowed to trade futures,
   or do I need an ETF wrapper? How big can the position be?)
2. **What's the next action?** (Paper-trade? Call the desk? Put an alert on a
   calendar spread?)
3. **Did I check the boring things?** (Stops, sizing, the half-life, the
   catalyst calendar, the vol-regime guardrail.)

The thesis answers "what do I think the market is doing?" The user's job is
"what do I do about it?" We've been optimising (1) and leaving (2) and (3) on
the floor.

## Why this matters now

The pass-2 quant review (2026-04-22) raised sizing to a $5m sleeve
*conditional* on closing the gap between thesis and execution. The vol-regime
guardrail we just shipped already caps size under high vol — but a desk user
who doesn't *see* that guardrail on the page can't use it at decision time.
The thesis has graduated from a curiosity to a sized bet. The UI hasn't.

## Alternatives considered

**A. Leave the thesis in a tab.** Today's state. Users have to go find it, and
it sits next to unrelated charts. Wins: zero work. Loses: the thesis is the
reason the product exists and it's buried behind navigation.

**B. Promote the thesis to a banner.** Ship a one-liner at the top of the
existing page — "Spread dislocated 2.8σ, mean-reversion bias, 4-day half-life."
Wins: low effort, visible to everyone. Loses: a banner can't hold the
materiality badge, the liveness annotation, the instruments, or the checklist.
It's either too long to be a banner or too short to drive action.

**C. Split the product into "Research mode" and "Execution mode".** Two
distinct modes; mode toggle in the sidebar. Wins: clean separation, lets each
mode be opinionated. Loses: a mode divide is a navigation decision that asks
the user to commit before they know what's going on. Also doubles the surface
area of the app.

**D. Hero placement + 3-tier instruments + checklist.** Move the thesis to the
top of the page. Below the thesis card, a small row of three instrument
suggestions scaled by risk appetite. Below that, a pre-trade checklist the
user can tick off. Everything else (macro arbitrage, depletion, fleet) stays
as tabs below. Wins: puts the decision-making content first, gives users a
graduated path from "I'm reading" → "I'm considering" → "I'm executing".
Loses: real UI work; risks crowding if we're not careful.

**Chosen:** D. Hero + 3-tier + checklist. The reason this wins over B is that
it addresses problems (2) and (3) above — not just visibility. The reason it
wins over C is that it doesn't force users into a mode before they know what
they're looking at.

## Why 3 tiers, not 1 or 5?

One tier is too blunt: "here's the trade" ignores that different users have
different mandates. Five tiers is granularity for its own sake — the user
doesn't want a sizing grid, they want a decision.

Three tiers matches how desks actually segment:

- **Tier 1 — Paper.** Track the thesis without putting capital at risk.
  Useful for a PM who wants to watch the hit-rate before sleeving capital.
- **Tier 2 — Instrument.** An ETF or calendar spread that gives oil-spread
  exposure without a futures licence. Most users live here.
- **Tier 3 — Futures.** Direct futures position (BZ=F / CL=F) with
  leverage. For users on a prop desk with a mandate.

Each tier is annotated with: size the thesis supports (after vol-regime
clamp), worst-case per-unit loss, and the specific instrument(s).

## Why a checklist, and why below the tiers?

A thesis + an instrument is still not an execution. The bugs we've shipped
against ourselves historically are boring things: forgetting to set a stop,
sizing past the vol-regime cap because the cap was implicit, trading into an
EIA release. A five-item checklist surfaces those boring things at the
decision point, which is the only point they matter. Below the tiers
because the user needs to choose a tier first to know what the checklist is
*for*.

## Assumptions we're making

1. **Users want a decision, not a dashboard.** This is the whole premise. If
   users actually want to graze through charts, hero placement is wrong. The
   pass-2 review said "I'd have asked for exactly this" — so this is
   evidence, not speculation, but still an assumption about the user.

2. **The current Trade Thesis JSON schema is stable enough to decorate.** We
   need to attach instruments and a checklist to an existing thesis. If the
   thesis schema is going to churn, we're building on sand. Checked: the
   schema hasn't changed since `5ec0b27 feat(thesis): upgraded models +
   streaming + materiality + history + dual-mode UI`.

3. **"Paper / ETF / Futures" maps to "most users' mandates".** This is a
   desk-centric assumption. If any of our users are retail or compliance-
   constrained in unusual ways, we'll need to revisit.

4. **The liveness annotation stays above the card.** We already shipped that
   in pass-2. Hero placement should preserve it, not replace it.

## Unknowns / open questions for Aidan

The following are open and should be resolved before the design spec is frozen:

1. **Tier-2 instrument: ETF or calendar spread?** USO/BNO is the obvious ETF
   pair; a WTI-Brent calendar spread is more direct but requires a futures
   account. My default: **both**, let the user pick. Aidan: confirm or pick one.

2. **Checklist items — exactly five?** I have a draft list (stop in place,
   size within vol-clamp, half-life understood, EIA catalyst ≥24h away, no
   conflicting thesis last 5 sessions). Aidan: confirm the five, or swap any.

3. **Click-through behaviour on a tier?** Options: (a) copy a TradingView/IB
   ticker to clipboard, (b) open a broker deeplink, (c) just show the symbol
   and notes inline. My default: (c), because (a) and (b) are execution
   integrations we haven't designed. Aidan: confirm (c), or a different scope.

4. **What happens to the existing "AI Insights" tab?** If the thesis is hero,
   that tab is redundant. Default: delete it. Aidan: confirm.

5. **Materiality gating — does it hide the entire hero, or just the
   instruments?** When the thesis isn't material (no dislocation), what does
   the user see? Default: a flat "no thesis today" card with the liveness
   annotation still showing. Aidan: confirm.

## What would prove this wrong?

- Users don't click on the instruments or tick the checklist — it becomes
  decorative noise. Measurement: add a simple counter event and watch a
  week of usage.
- The checklist becomes a confirmation-bias machine — users tick without
  thinking. Measurement: random audits of checked-but-failed trades.
- Hero placement pushes the macro/depletion/fleet tabs into disuse, but
  those tabs are where the thesis is *formed*. Measurement: tab engagement
  before/after.

If any of these come true, we revise — likely toward option C (two modes)
rather than reverting all the way to A (status quo).

## Next step

Aidan reviews this brainstorm. Responds with answers to the five open
questions above. Then the design spec at `docs/designs/hero-thesis.md`
freezes, and the plan at `docs/plans/hero-thesis.md` slices the work.

Until then — per the `brainstorming` skill's HARD-GATE — no implementation
begins.
