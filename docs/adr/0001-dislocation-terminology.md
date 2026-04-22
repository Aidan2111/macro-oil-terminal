# ADR 0001: Plain-language "dislocation" label

* Status: accepted
* Date: 2026-04-21
* Deciders: @Aidan2111, desk-quant persona

## Context

The first two product revisions exposed raw statistical jargon on the
surface — "Z-score", "mean reversion", "Sharpe ratio", "R²". That's fine
for a quant audience, but the target reader is a generalist trader or PM
who wants decision support without a statistics refresher. Early user
feedback: "half my analysts stopped reading at `|Z| > 2σ`."

## Decision

Relabel the entire UI to finance-first language, keep the math
identical, and provide an **Advanced metrics** sidebar toggle that
restores the technical labels inline. Every renamed metric carries a
`help=` tooltip with the precise statistical definition.

Key translation table:

| Raw term | UI label |
|---|---|
| Z-score | Dislocation |
| Mean reversion | Snap-back to normal |
| Sharpe ratio | Risk-adjusted return |
| Max drawdown | Biggest losing streak |
| R² | Trend fit quality |
| `long_spread` / `short_spread` / `flat` | BUY / SELL / STAND ASIDE |
| Invalidation risks | What would make us wrong |
| Catalyst watchlist | Upcoming events to watch |

Internal Python identifiers (`Z_Score`, `stance`, `conviction_0_to_10`)
stay stable — the rename is **UI-only**, applied at the render boundary.
This protects the JSON schema, the audit log shape, and every
downstream test.

## Consequences

**Positive:**

- Dashboard is readable by non-quants without explanation.
- No churn in the audit-log format (`data/trade_theses.jsonl`) or test
  fixtures — same dataclass, different presentation.
- The Advanced toggle gives the quant audience a single click back.

**Negative / trade-offs:**

- Two sets of labels to maintain; contributors need to remember to
  relabel at the render boundary, not rename Python symbols. The
  `ui: plain-language pass` commit + `CONTRIBUTING.md` data-policy
  section enforce this.
- The LLM system prompt now instructs the model to prefer plain-language
  terms in prose output — if we swap models, that behaviour has to be
  re-validated.

## Alternatives considered

- **Dual-mode always** — render both labels side-by-side. Rejected:
  clutter, and hides the decision rather than making it.
- **Rename code-level too** — rejected to preserve audit-log schema and
  downstream integrations.

## References

- Commit `a060db4` — `ui: plain-language pass — rename Z-score to Dislocation, add tooltips`
- `quant_review_2026-04-22.md` ("What's right — don't break these" #1)
