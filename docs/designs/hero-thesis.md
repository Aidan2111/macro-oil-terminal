# Hero Trade Thesis + Executable Instruments — Design Spec

> **Status:** DRAFT — pending Aidan's answers to the five open questions in
> `docs/brainstorms/hero-thesis.md`. Review time target: 5 minutes.

## Goal

Promote the Trade Thesis from a tab to the hero of the page, and ship it
with a graduated execution path (three instrument tiers + a five-item
pre-trade checklist). The user's mental loop becomes: *read the thesis → pick
a tier appropriate to their mandate → run the checklist → act.*

## Ships

### UI (`app.py`)

1. **Hero band** renders at the top of the page above the existing tab bar,
   on every tab. Contents, top-to-bottom:
   - Liveness annotation (already-shipped, unchanged).
   - Thesis card: stance pill, conviction bar, time-horizon chip, materiality
     badge, 2-3 sentence summary, "why this now" bullet list.
   - Three instrument tiles (tier 1/2/3), horizontally arranged.
   - Pre-trade checklist — 5 items, checkboxes, stateful within the session.
2. **Tabs remain below** the hero. No tab is renamed in this change.
3. **"AI Insights" tab is deleted.** Its content has been hero for several
   months; the tab is redundant. (Confirms brainstorm question 4.)
4. **Materiality gating:** when the thesis is `stance="flat"` AND
   materiality badge is "low", the hero shows a flat card ("No tradeable
   dislocation today. Next EIA release: X.") and instruments + checklist are
   hidden. Liveness annotation still renders. (Confirms brainstorm question 5.)

### Schema (`trade_thesis.py`)

The `Thesis` dataclass gains two decorated fields, both populated by a new
pure function — **not** by the LLM. The LLM output remains unchanged.

```python
@dataclass
class Thesis:
    # ... existing fields unchanged ...
    instruments: list[Instrument] = field(default_factory=list)   # NEW
    checklist: list[ChecklistItem] = field(default_factory=list)  # NEW

@dataclass
class Instrument:
    tier: int                  # 1, 2, or 3
    name: str                  # "Paper", "USO/BNO ETF pair", "CL=F futures"
    symbol: Optional[str]      # None for paper tier
    rationale: str             # one sentence
    suggested_size_pct: float  # post-vol-clamp percentage of capital
    worst_case_per_unit: str   # "$X per contract" / "N/A"

@dataclass
class ChecklistItem:
    key: str                   # stable identifier: "stop_in_place", "vol_clamp_ok", ...
    prompt: str                # user-visible text
    auto_check: Optional[bool] # if the system already knows the answer, preset it
```

The `decorate_thesis_for_execution(thesis, ctx)` helper is a pure function
that takes an existing `Thesis` + a `ThesisContext` and returns a copy with
`instruments` and `checklist` populated. Rules:

- If `stance == "flat"` → empty instruments, empty checklist. (Materiality
  gating drives this.)
- Otherwise, three instruments always, keyed by tier:
  - Tier 1 (Paper): always populated. Size = suggested_pct_of_capital * 0.
  - Tier 2 (ETF): populated with "USO/BNO pair" for `long_spread`, inverted
    for `short_spread`. Size = suggested_pct_of_capital * 0.5.
  - Tier 3 (Futures): `BZ=F`/`CL=F` calendar pair. Size =
    suggested_pct_of_capital * 1.0 (already clamped by guardrails upstream).
- Checklist items (always these five, fixed order):
  1. `stop_in_place` — "I have a stop at ±2σ spread move from entry."
  2. `vol_clamp_ok` — auto-checked when `ctx.vol_brent_30d_pct` is below its
     1y 85th percentile (the vol-regime guardrail is silent).
  3. `half_life_ack` — "I understand the implied half-life is ~N days."
  4. `catalyst_clear` — auto-checked when the next EIA release is ≥24 hours
     away per `ctx.hours_to_next_eia` (new field; see below).
  5. `no_conflicting_recent_thesis` — auto-checked when the last 5 thesis
     history entries don't include a stance flip.

### Context (`thesis_context.py`)

- Add `hours_to_next_eia: Optional[float]` to `ThesisContext`. Computed from
  the existing EIA release calendar — Wednesdays at 14:30 UTC (standard)
  with DST shifts. Nullable for when the calendar feed is unavailable.

### Tests

- `tests/unit/test_hero_thesis_decoration.py`
  - `test_decorate_flat_thesis_returns_empty_instruments_and_checklist`
  - `test_decorate_long_spread_produces_three_tiers`
  - `test_decorate_short_spread_inverts_etf_pair`
  - `test_decorate_clamps_tier3_size_to_thesis_suggested_pct`
  - `test_decorate_checklist_auto_checks_vol_clamp_when_vol_below_p85`
  - `test_decorate_checklist_auto_checks_catalyst_when_eia_over_24h`
- `tests/unit/test_thesis_context.py`
  - `test_thesis_context_computes_hours_to_next_eia_for_known_wednesday`
  - `test_thesis_context_hours_to_next_eia_nullable_when_calendar_missing`
- `tests/e2e/` (Playwright)
  - `test_hero_band_renders_above_tabs`
  - `test_hero_band_hidden_on_flat_thesis`
  - `test_checklist_checkbox_persists_within_session`

### Monitoring / alerts

- One new App Insights counter event: `hero_checklist_checked` with
  properties `{ key, auto }`. No new alert rule — we'll watch volume for a
  week and then decide.

### Rollback

- UI change is additive until the "AI Insights" tab is deleted. That
  deletion lands in its own commit so rollback is a git revert of one SHA.
- Schema change is additive — `instruments` and `checklist` default to empty
  lists, so older consumers of `Thesis` keep working.
- Env vars / secrets: none.

## Out of scope (YAGNI)

- Broker deeplinks and TradingView handoff (brainstorm question 3 picked
  inline-display-only).
- Checklist items that require external data we don't already have.
- A/B testing between hero-band and the old tab layout.
- User-configurable checklist items.
- Persisting checklist state across sessions (session-only is fine).

## Open items from brainstorm

Three answers are required before the plan is sliced:

1. **Tier 2 instrument:** ETF pair (USO/BNO) proposed. Aidan may pick
   calendar spread instead, or both.
2. **Checklist's five items:** listed above. Aidan may swap any.
3. **Click-through:** inline-display only. Aidan may scope in a broker
   deeplink.

Questions 4 (delete AI Insights) and 5 (materiality gating of instruments)
are answered above; Aidan may override.

## Review

Aidan reviews this spec. Questions answered, changes applied, spec
re-committed. Then the plan at `docs/plans/hero-thesis.md` freezes and
implementation begins (TDD, one task at a time).
