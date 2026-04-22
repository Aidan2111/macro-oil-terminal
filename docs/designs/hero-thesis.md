# Hero Trade Thesis + Executable Instruments — Design Spec

> **Status:** APPROVED (2026-04-22). All five brainstorm questions
> resolved with conservative defaults; see the bottom of the brainstorm
> for the full answer set. Implementation proceeds per
> `docs/plans/hero-thesis.md`.

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
   - **Portfolio sizing widget** — one `st.number_input` labelled "Portfolio
     (USD)", default **$100,000**, stored in
     `st.session_state["hero_portfolio_usd"]`. Every tier-tile dollar
     figure multiplies against this input.
   - Three instrument tiles (tier 1/2/3), horizontally arranged. Each tile
     renders: tier badge, instrument name, symbol (where applicable), the
     `rationale` copy, the suggested position size as both a % of capital
     *and* an absolute USD using the portfolio widget above, and a small
     row of four broker search-links (IBKR / Schwab / Fidelity /
     TastyTrade) that linkify to each broker's own symbol lookup.
     The Tier-2 tile additionally renders a single static caption with the
     defined-risk options pattern: "Defined-risk alt: ATM ± 2 strikes on
     BNO/USO, 30–60 DTE, OI > 100." No live options chain — intentional YAGNI.
   - Pre-trade checklist — 5 items, checkboxes, stateful within the session.
     Each tick appends one row to `data/trade_executions.jsonl` (gitignored):
     `{ts_utc, thesis_fingerprint, checklist_key, checked_by_user,
     auto_check_value}`.
   - **Disclaimer caption** immediately below the hero, always visible:
     *"Research & education only. Not personalized financial advice.
     Futures and options can lose more than the initial investment. Past
     performance does not predict future results. Consult a licensed
     advisor before executing. Data may be 15-min delayed."*
2. **Tabs remain below** the hero. No tab is renamed in this change.
3. **"AI Insights" tab is deleted.** Its content has been hero for several
   months; the tab is redundant. Lands in its own commit inside Task 6 so
   the deletion is a clean single-SHA revert target.
4. **Materiality gating:** when the thesis is `stance="flat"` the hero
   still renders but instruments + checklist are hidden. Flat card reads:
   *"No tradeable dislocation today. Next EIA release in Xh."* Liveness
   annotation still renders. The disclaimer caption still renders.

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

- **Actual broker order submission** — the four broker "links" are
  search/lookup anchors only, never auto-submit. Any change to that
  policy is a separate design.
- **Live options-chain pull** — the Tier-2 defined-risk line is a
  static pattern reminder. Pulling real options data is its own
  provider + cost conversation.
- **TradingView handoff / clipboard ticker copy** — not in scope.
- Checklist items that require external data we don't already have.
- A/B testing between hero-band and the old tab layout.
- User-configurable checklist items.
- Persisting checklist state across browser sessions (session-only is
  fine; the append-only `trade_executions.jsonl` is the durable record).

## Resolved items (from brainstorm)

All five brainstorm questions resolved 2026-04-22 with conservative
defaults. The full answer set — including the six extra defaults Aidan
pre-empted (portfolio size, disclaimer wording, broker deep-links,
options-tier strike rule, checklist persistence scope, and a residual
"most conservative, minimal, reversible" rule) — lives at the bottom
of `docs/brainstorms/hero-thesis.md` under "Status: RESOLVED".

Applied to this spec above: portfolio sizing widget, disclaimer
caption, broker search-link row on each tier, Tier-2 defined-risk
options pattern caption, ETF-pair-as-default with a calendar-spread
note line, single-commit deletion of the "AI Insights" tab inside
Task 6, and the `trade_executions.jsonl` append-only log hook on
every checklist tick.

## Review

This spec is frozen. Implementation proceeds per
`docs/plans/hero-thesis.md`, one task at a time, TDD per Superpowers
`subagent-driven-development`.
