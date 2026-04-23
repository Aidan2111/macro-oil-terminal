# ADR 0004 — Market-data provider decision

- **Status:** Accepted (2026-04-23).
- **Decision drivers:** Cost, coverage of crude futures (BZ=F / CL=F),
  reliability, and lock-in risk.
- **Alternatives considered:** Massive, Databento, yfinance, Twelve
  Data, Polygon.

## Decision

**yfinance remains the primary market-data provider for crude
futures (BZ=F, CL=F) for this phase.** Twelve Data and Polygon stay
as optional fallbacks behind env-gated provider keys (already in
place since `providers/_twelvedata.py` and `providers/_polygon.py`).

Databento is on the shelf: an API key has been provisioned
(`DATABENTO_API_KEY` in `.env` and on both webapps) and live-validated
(29 datasets accessible). No code depends on it yet. Any future
upgrade of the pricing core to Databento is a one-branch swap —
add a `providers/_databento.py` that implements the same
`fetch_daily` / `fetch_intraday` / `health_check` surface and flip
the orchestrator's priority order.

Massive was considered briefly and rejected without any code
scaffolded.

## Rationale

### Why yfinance over Databento (today)

- **Cost.** Databento's subscription + per-symbol, per-schema, per-
  month pricing exceeds what this phase justifies. yfinance is free
  and the data is sufficient for daily-resolution dislocation
  analytics + 15-minute delayed intraday. The `(15-min delayed)`
  caveat is surfaced in the UI.
- **Latency of signal.** Our core models are daily bars and a 1-minute
  intraday tape for the live ticker. Databento's sub-second
  resolution and options-chain granularity are overkill for
  "spread stretch Z-score crosses a threshold" signals that run
  once a minute at most.
- **Coverage gap isn't actually blocking.** Databento's `GLBX.MDP3`
  (CME) + `IFEU.IMPACT` (ICE Europe) give authoritative tick-level
  futures data — a future advantage — but for now yfinance's
  BZ=F / CL=F continuous-front-month coverage matches what the
  models consume.

### Why the key stays provisioned

Cost decisions flip. If revenue or a real user base lands, upgrading
to Databento for tick-level futures + options chains becomes a
one-day swap. Keeping the key provisioned (and the smoke-tested
SDK path ready in our toolbox) means the upgrade path is validated
without blocking today's cost ceiling.

### Why not Massive

Primarily equities-focused; crude futures wasn't its sweet spot. We
never built scaffolding.

## Consequences

- The **Data Sources sidebar** continues to read:
  - Pricing: `yfinance (BZ=F, CL=F)` as the live provider; Twelve Data
    / Polygon as key-gated fallbacks.
- No `providers/_databento.py` ships yet.
- Every UI surface referring to market data says **"Yahoo Finance
  (15-min delayed)"** or similar plain-English explicitly. No
  "Databento live" or "Massive" captions.
- The `DATABENTO_API_KEY` App Setting is present on both webapps but
  unread by any code path. If a reviewer sees it, that's the
  contract: provisioned-but-dormant.

## Revisit triggers

- A paying user asks for sub-second fills in the live ticker.
- The product needs intraday options chains on CL/BZ (Databento's
  options coverage is the obvious fit).
- yfinance's rate limiting becomes a real-world blocker in the
  live ticker fragment.

## References

- Databento pricing: https://databento.com/pricing
- yfinance: https://github.com/ranaroussi/yfinance
- Providers orchestrator: `providers/pricing.py`
- `.env.example`: see `TWELVEDATA_API_KEY`, `POLYGON_API_KEY`
  (optional fallbacks).
