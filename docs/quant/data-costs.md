# Data subscription costs (issue #105 / #106 / #107)

Tier 4 of the quality plan adds paid data sources to break the
single-provider dependency on yfinance for prices and AISStream for
ship tracking. This doc tracks the monthly cost surface so the
budget conversation is explicit.

## Active subscriptions

| Provider | Plan | Monthly cost | What it gives us | Env var |
|---|---|---|---|---|
| Databento | Stocks Starter + Futures (CME + ICE Europe) | ~$29-79 | Real-time CL/BZ tick data; replaces yfinance's 15-min-delayed feed as the primary intraday source | `DATABENTO_API_KEY` |
| Twelve Data | Free tier (800 calls/day) | $0 | Third price-corroboration source; triangulates against yfinance + FRED. Issue #106 wires this in. | `TWELVEDATA_API_KEY` |
| AIS redundancy | TBD (Spire / MarineTraffic) | TBD | Second AIS feed so a single-provider silence (the 4-day AISStream outage that triggered #93) doesn't blank the fleet tile. Issue #107 surveys candidates. | TBD |

## Free / existing sources

- **yfinance** — free, 15-min-delayed; demoted to fallback for prices.
- **FRED** (`FRED_API_KEY`) — free, next-business-day. Currently powers issue #97 corroboration.
- **EIA v2 + STEO** (`EIA_API_KEY`) — free, weekly cadence.
- **CFTC** — free public CSV.
- **AISStream** (`AISSTREAM_API_KEY`) — free websocket, currently the sole AIS source until #107 lands.
- **OFAC SDN** — free public CSV.
- **News RSS** — free.
- **Azure OpenAI Foundry** (`FOUNDRY_API_KEY`) — pay-as-you-go per-call. ~$0.05-0.20 per thesis. Cost-bounded by the keep-warm cron not pinging `/api/thesis/generate` and by the synthetic monitor running every 15 min.

## Onboarding flow for a new paid source

1. Provision the key out-of-band; add to Azure App Service config + GH Actions secret.
2. Add the provider module under `providers/_<name>.py` with a lazy SDK import + key gate.
3. Register the provider in `providers/pricing.py` (or the equivalent orchestrator) with a try/except fall-through to the existing free source.
4. Document the cost above + add the env var to `.env.example`.
5. The new provider should be a strict superset of capability — turning the key off must not break the deployment.

## Reviewing this doc

Update on every paid-source change (subscription up/downgrade, new provider, deprecated tier). Aidan owns the billing relationship; this doc is the single source of truth for "what does the system cost to run".
