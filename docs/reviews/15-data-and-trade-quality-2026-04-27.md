# Review 15 — Data quality, Trade info, Prediction quality (live audit)

**Date:** 2026-04-27 (Mon, 17:18–17:25Z)
**Reviewer:** Claude (read-only audit)
**Build under test:** `45c8a22` · region `canadaeast` · mode `live`
**Live frontend:** https://delightful-pebble-00d8eb30f.7.azurestaticapps.net/
**Live API:** https://oil-tracker-api-canadaeast-0f18.azurewebsites.net/

**Top-level verdict: NEEDS-ATTENTION.** The quant pipeline (cointegration, half-life, GARCH, regime classification, backtest) is computing real, sensible numbers and the hero card cites them correctly. But three of the four "Q" workstreams shipped earlier this session have visible gaps in the production output: the Data Quality endpoint is stubbed (every provider amber, every metric `null`), the Tier 1/2/3 trade-instrument decoration is never invoked by the live thesis path (so `instruments: []`), and three risk metrics in `/api/backtest` (VaR-95, ES-95, ES-97.5, max-drawdown) all return the same number — they collapse to a single quantity. None of these are *wrong* enough to mislead a careful reader, but they do mean the surface area Aidan's been watching is showing less than it claims.

Screenshots of every route captured at audit time are saved alongside this doc under `quality-review-2026-04-27/`.

---

## 1. Data quality scorecard (Q1 — `/api/data-quality`)

`curl -sS .../api/data-quality` at 17:17:13Z returns the schema correctly but every provider is identical:

| Provider     | Status (live API) | last_good_at | n_obs | latency_ms | message | freshness target | Frontend tile     |
|--------------|-------------------|--------------|-------|------------|---------|------------------|-------------------|
| yfinance     | amber             | null         | null  | null       | null    | 6 h              | green dot, "3m ago" |
| eia          | amber             | null         | null  | null       | null    | 192 h            | amber dot, "—"    |
| cftc         | amber             | null         | null  | null       | null    | 192 h            | amber dot, "—"    |
| aisstream    | amber             | null         | null  | null       | null    | 0.083 h (5 min)  | amber dot, "—"    |
| alpaca_paper | amber             | null         | null  | null       | null    | 0.25 h (15 min)  | amber dot, "—"    |
| audit_log    | amber             | null         | null  | null       | null    | 24 h             | (not surfaced)    |

`overall: amber`, `generated_at: 2026-04-27T17:17:13Z`. **Every per-provider field is null** — no last_good_at, no observation count, no latency, no sanity-check message. The endpoint is rendering its schema with placeholder values; the actual provider tracking that the Q1 work was supposed to wire up is not in production.

Cross-source sanity checks the user prompt asks about (yfinance WTI vs EIA `PET.RWTC.D`, spread bounds `[-30, +50]`, inventory week-over-week >15M bbl, dislocation >6) cannot be evaluated from this endpoint as currently implemented — there's no code path emitting the violations.

**Independent checks against other endpoints** (i.e. what the Data Quality tile *could* be reporting):

- **yfinance / spread**: `as_of: 2026-04-24` (Friday close, 3 calendar days old at audit time). For a Mon morning the latest US close is 04-24, so this is correct. But it exceeds the declared 6 h freshness target — the hero pill shouldn't be green for yfinance unless the freshness target gets relaxed to "last business close".
- **EIA inventory**: `as_of: 2026-04-17`, source EIA. Last release is the Wed 04-22 weekly for week ending 04-17. 192 h target → 8 days; we're at ~10 days. This is mildly stale but inside the next-release window (next EIA release stamped 2026-04-29 per thesis context). Fine.
- **CFTC positioning**: `as_of: 2026-04-21`, weekly disaggregated COT for the 2026 zip. Releases Friday afternoon for prior Tuesday. 04-25 release → 04-21 reference is correct. 192 h target met.
- **AISStream / fleet**: `n_vessels: 0`, `last_message_seconds_ago: 0`, `vessels: []`, source `aisstream`. The 5-minute freshness target is meaningless when zero messages have ever been received. The corroborating `/api/fleet/categories` endpoint returns 0/0/0/0/0. AISStream is effectively unconnected.
- **Alpaca paper**: `/api/positions/account` returns `{buying_power: 200000, cash: 100000, equity: 100000, status: ACTIVE, paper: true}` — provider works.
- **audit_log**: `/api/thesis/history` returns >0 theses; `/api/thesis/latest` returns a record at 2026-04-27T15:21:09Z. Provider works.

The frontend Data Quality tile shows a **green dot for yfinance** with "3m ago" but **amber dots for the rest** — which is inconsistent with the API response (which says everything is amber and everything is null). The frontend is probably hand-rolling its own status from per-endpoint payloads instead of trusting `/api/data-quality`. That's defensible behavior but means the endpoint and the tile are computing two different things.

**Severity:** medium — data is real; the gauge that's supposed to *prove* it's real is empty.

---

## 2. Trade info accuracy (Q2 — `/api/thesis/*`)

Three samples were captured: the persisted `/api/thesis/latest` record (gen at 15:21Z) plus two fresh streams via `POST /api/thesis/generate` (17:21Z, fingerprint `a283…`) and `POST /api/thesis/regenerate` (17:24Z, fingerprint `2c9e…`).

### 2.1 Hero card content (qualitative)

All three samples produced the same stance (`short_spread`), same conviction (5/10), and time horizons of 14–21 days. Plain-English headlines were variants of "Brent is about $11 above WTI — consider a small bet that the gap narrows".

The hero card's quant chips render correctly (verified via screenshot crop):

- **Stance pill:** "LEAN SHORT" ✓
- **Cointegration pill:** "Coint p=.057 (HL 9.2d)" — matches API `coint_p_value=0.05738`, `coint_half_life_days=9.234`. The pill correctly flags weak cointegration via the amber-yellow color.
- **Term-structure badge:** "CONTANGO" ✓ (matches `regime_term_structure: contango`)
- **Vol-bucket badge:** "HIGH VOL" (red) ✓ (matches `regime_vol_bucket: high`, `regime_vol_percentile: 90.5`)
- **Rolling-z chip:** "ROLLING z=1.32" ✓ (matches `current_z`)
- **Confidence bar:** Medium (5/10) ✓
- **Horizon:** 21 days ✓

The body text on the live card cites the same numbers correctly: "GARCH-normalised stretch of 1.44 (garch_z=1.4359) and a 90d rolling stretch of 1.32; the Engle-Granger test (p=0.057, half-life ~9 days) shows weak cointegration so a snap-back to normal over the next 2-3 weeks is plausible. Short the Brent-WTI gap (bet it narrows) sized small because the futures curve is in contango and overall volatility is high." Every numeric quoted matches the source context object.

### 2.2 Tier 1 / Tier 2 / Tier 3 instruments — **the gap**

The user prompt asks for line-by-line verification of:
- Tier 1 futures contract symbol vs CME calendar (CL should be `CLM6` or `CLN6` on 2026-04-27)
- Tier 2 ETF prices for `BNO` / `USO`, freshness within 60s
- Tier 3 options chain — strikes ATM±2, OI > 100, expiry 30–60 DTE
- Notional / margin math
- Citation of cointegration + half-life

**The first four bullets cannot be checked because the live API never populates `instruments` or `checklist`.** Both sample SSE `done` payloads return:

```json
"instruments": [],
"checklist": []
```

The decoration code exists (`trade_thesis.py:380` `decorate_thesis_for_execution(...)`) and would emit three placeholder Instrument rows for non-flat stances (Tier 1 "Paper", Tier 2 "USO/BNO ETF pair", Tier 3 "CL=F / BZ=F futures"). But:

1. The service path `backend/services/thesis_service.py :: stream_thesis()` **never imports or calls `decorate_thesis_for_execution`**. `grep -n decorate_thesis backend/services/thesis_service.py` returns nothing.
2. Even if it did, the Tier 2 / Tier 3 instruments are *templates* — symbol `"USO/BNO"` and `"CL=F/BZ=F"` are continuous-contract aliases, not actual front-month codes. `worst_case_per_unit` for Tier 2 is the literal string `"~$X per $1k notional"`. There is no live price fetch, no OI lookup, no DTE calculation, no notional or margin math.

Net effect on the live site: the hero card's `PRE-TRADE CHECKLIST` block renders five items ("Stop set at ≥2σ from entry", "Realised vol below the 1y 85th percentile", "Implied half-life is acceptable for the horizon", "Next EIA release is more than 24 h away", "No stance flip in the last 5 theses"). Those items do appear, so the frontend has a hardcoded fallback or is drawing from somewhere other than `instruments`/`checklist`. But the actual Tier 1/2/3 *trade tickets* the prompt asks about don't exist in the rendered output; the card never tells the user "buy CLM6 at $94.40, sell BZM6 at $105.33".

### 2.3 Citations — pass

Every thesis text body cites the live cointegration p-value (0.057), half-life (~9d), GARCH-normalised z (1.436), regime tags, current spread ($10.93), 90-day mean ($5.35), CFTC managed-money net (99,887 contracts), Cushing 4-week slope (-42,714 bbl/d), and inventory totals. The numbers are not hallucinated — they trace back to `/api/spread`, `/api/inventory`, `/api/cftc`, and the embedded thesis-context object exactly.

The thesis also correctly self-flags two real defects in its own `data_caveats`:

> "Backtest metrics are empty (bt_hit_rate=0) — no historical trade-sample validated here."
> "Fleet data incomplete (fleet_source empty; fleet counts zero) — no tanker-flow signal available from provided data."

Both caveats are accurate (see §3.3 and §1 above).

**Severity:** medium-high — the qualitative thesis is solid and well-cited, but the trade-execution layer that "Q2 trade-info accuracy" was supposed to deliver is not wired into the live API.

---

## 3. Prediction quality (Q3)

### 3.1 Spread / cointegration / half-life — pass (with caveats)

`/api/spread` at 17:17Z:

- Brent: `$105.33` · WTI: `$94.40` · spread: `$10.93` · stretch (z): `1.3236` · band: `Stretched` · `as_of: 2026-04-24` · source `yfinance` · 90 history points.
- Cointegration p-value `0.0574` — borderline weak (>0.05). The thesis correctly downgrades conviction and labels the verdict `weak`.
- Half-life: `9.23 days`. Hedge ratio: `1.0102`. Both reasonable for Brent-WTI on a 90-day window.

Note: **`/api/spread` itself does not return cointegration p-value or half-life.** Its keys are `[as_of, brent, brent_price, fetched_at, history, series, source, spread, spread_usd, stretch, stretch_band, wti, wti_price]`. Those fields surface only inside the `thesis.context` object served by `/api/thesis/latest`. The user prompt assumes `/api/data-quality` cites them — it doesn't. If a frontend other than the hero card needs cointegration / half-life, it has no API endpoint to call.

### 3.2 Regime classification — pass

From the thesis context:
- `regime_term_structure: contango` ✓
- `regime_vol_bucket: high`, `regime_vol_percentile: 90.48` ✓
- `garch_z: 1.4359`, `garch_ok: true`, `garch_persistence: 0.9908`, `garch_sigma: 3.89`, `garch_fallback_reason: null` ✓ (good — high persistence is consistent with the high-vol regime)

### 3.3 Backtest — partial pass (risk metrics broken)

`POST /api/backtest` with `{z_threshold:2.0, lookback_days:90, start_date:"2024-01-01"}`:

| Metric              | Value           | Matches PROGRESS.md? |
|---------------------|-----------------|----------------------|
| n_trades            | 31              | yes                  |
| Sharpe              | 4.376           | yes (PROGRESS: 4.38) |
| Sortino             | 31.003          | yes (PROGRESS: 31.0) |
| Calmar              | 15.529          | n/a                  |
| Hit rate            | 90.32 %         | yes (PROGRESS: 90.3%) |
| Total PnL (USD)     | $431,037.61     | yes (PROGRESS: $431k)|
| Avg PnL per bbl     | $1.39           | n/a                  |
| Avg days held       | 19.81           | n/a                  |
| Equity curve length | 31 points       | yes                  |
| Rolling 12 m Sharpe | 6.15 (scalar!)  | likely intended as series |

**Risk metrics are degenerate:**

```
"var_95":       -5701.94,
"es_95":        -5701.94,
"es_975":       -5701.94,
"max_drawdown": -5701.94,
```

Four distinct quantities, identical to the dollar. Replicated on the macro page screenshot for a different parameter combo (where all three rendered as `-$4,302`). VaR-95 (5th-percentile loss), ES-95 (mean of the worst 5%), ES-97.5 (mean of the worst 2.5%), and max drawdown are mathematically distinct on any non-trivial PnL distribution; collapsing them to one number means the implementation is returning the same value (probably the worst-trade PnL or the trough of the equity curve) for all four.

Also: `rolling_12m_sharpe` is `6.152970094905503` — a single scalar — not the time series the field name suggests. The frontend may be expecting a series for trend rendering.

The macro page screenshot shows backtest tiles with **Sharpe 1.71, Sortino 44.53, Calmar 19.46, Hit rate 89.3%, Max DD $-4,302, VaR-95 $-4,302, ES-97.5 $-4,302** — confirming both that distinct parameter sets produce different (real) values and that the three risk metrics still collapse to a single number under that parameter set.

The default-parameter Sharpe (1.71 on the macro tile) is materially lower than the user-parameter Sharpe (4.38). Both are credible — short lookback + tight Z threshold cherry-picks high-Sharpe regimes — but the discrepancy is worth noting because the front-page tile uses one set and the on-demand backtest uses another, which can confuse a reader who expects the frontline Sharpe to match what the thesis cites.

### 3.4 Track-record sharpe (signal vs backtest) — pass

The Track-Record page tile reads `SHARPE (SIGNAL): 0.00` (signal Sharpe is computed over executed trades, of which there are zero). The macro-page Sharpe is the backtest Sharpe (1.71). Two different numbers, both intentionally different — fine, but the labels could be clearer.

**Severity:** medium — quant outputs are right; the four-way tie on risk metrics is a reproducible bug.

---

## 4. Confidence calibration (Q4)

`/api/calibration` at 17:18Z:

```json
{
  "n_total": 0,
  "brier_score": 0.0,
  "mean_signed_error": 0.0,
  "verdict": "insufficient_data",
  "buckets": [
    {"label":"0-25%",   "lo":0.0,  "hi":0.25,  "midpoint":0.125, "n":0, "hits":0, "hit_rate":0.0},
    {"label":"25-50%",  "lo":0.25, "hi":0.5,   "midpoint":0.375, "n":0, "hits":0, "hit_rate":0.0},
    {"label":"50-75%",  "lo":0.5,  "hi":0.75,  "midpoint":0.625, "n":0, "hits":0, "hit_rate":0.0},
    {"label":"75-100%", "lo":0.75, "hi":1.001, "midpoint":0.875, "n":0, "hits":0, "hit_rate":0.0}
  ]
}
```

Schema is correct: four buckets present (0-25 / 25-50 / 50-75 / 75-100), Brier and signed error fields exist, verdict label is in the prescribed enum. The frontend's CONFIDENCE CALIBRATION block (Track Record page) reads `Brier 0.000 · signed error 0.0% · n=0` with a `not enough data` badge and the dotted "ideal" diagonal — exact correspondence to the API. The reliability diagram is rendered as the four x-axis tick labels.

Returning `verdict: "insufficient_data"` is the right thing to do until predictions accumulate. There is nothing to calibrate against because (a) `/api/positions/orders` is empty (no executed trades) and (b) thesis history doesn't yet include a verified outcome record. Calibration plumbing works; it's just empty.

**Severity:** none (correct empty-state).

---

## 5. Findings + recommendations (severity-ranked)

### What's solid (highlights)

1. **Quant pipeline is mathematically real.** Engle-Granger, GARCH(1,1) (`persistence 0.991`, `sigma 3.89`), 90-day rolling z-score, regime classifier, and the Brent-WTI mean-reversion backtest all return values consistent with PROGRESS.md (Sharpe 4.38, Sortino 31.0, hit rate 90.3%, $431k PnL on user params). 31 trades over 5 years.
2. **Hero card renders accurate citations.** `Coint p=.057 (HL 9.2d)` · `CONTANGO` · `HIGH VOL` · `ROLLING z=1.32` · `Confidence Medium 5/10` — every chip ties to a real value in `/api/spread` or `/api/thesis/latest.context`.
3. **Real fundamental data flows.** EIA inventory `commercial 465.7 Mbbl`, `Cushing 30.6 Mbbl` (slope -42,714 bbl/d), `SPR 405.0 Mbbl` — all match latest releases. CFTC managed-money net `99,887` (3y z `-0.165`) at `as_of 2026-04-21` is the correct prior-Tuesday reference for a Friday 04-25 release.
4. **Calibration framework correctly returns "insufficient_data" with all 4 buckets present.** No fake confidence numbers.
5. **Generation latency is acceptable.** 60.6 s and 65.3 s for the two SSE generations — slow but not broken. SSE event protocol (`progress` → `delta` → `done`) is well-formed, and keepalives prevent gateway timeouts.

### Issues found (severity-ranked)

| # | Severity | Where | Finding | Recommendation |
|---|----------|-------|---------|----------------|
| 1 | **HIGH** | `/api/backtest` | VaR-95, ES-95, ES-97.5, and max-drawdown all return the **same dollar value** (`-5701.94` on user params, `-4302` on macro defaults). They're mathematically distinct and should differ. Implementation likely reduces all four to max DD or worst trade. | Recompute VaR/ES from the **trade PnL distribution** (or daily equity-curve returns) using the appropriate quantile / expected-shortfall formulas; keep max-drawdown as a separate trough-from-peak walk on the equity curve. Add a unit test that VaR-95 ≠ ES-97.5 ≠ max-DD on synthetic non-degenerate PnL. |
| 2 | **HIGH** | `/api/thesis/generate` SSE `done` | `instruments: []` and `checklist: []` always — the Q2 trade-info layer was never wired in. `decorate_thesis_for_execution` exists in `trade_thesis.py:380` but is not called from `backend/services/thesis_service.py`. | Either (a) hook `decorate_thesis_for_execution(thesis, ctx)` into `stream_thesis()` *and* upgrade the placeholder Instrument templates to fetch live front-month futures codes (`CLM6`/`BZM6` per CME calendar today), live BNO/USO marks via yfinance, ATM±2 option chain via `yfinance.Ticker.options` with OI filter and 30–60 DTE, and compute notional + margin from the position-sizing %. Or (b) drop the Tier 1/2/3 ambition from the spec until those data feeds are real. The current half-shipped state means the hero card promises "executable trade ideas" but never delivers symbols. |
| 3 | **HIGH** | `/api/data-quality` | Every provider returns `status: amber` with `last_good_at`, `n_obs`, `latency_ms`, `message` all `null`. The endpoint is a schema with no fill. | Wire each provider's actual fetch to update a per-source state object (last successful timestamp, observation count, latency, last sanity-check verdict). At minimum: yfinance from `/api/spread.fetched_at`, EIA from `/api/inventory.as_of`, CFTC from `/api/cftc.as_of`, AISStream from `last_message_seconds_ago`, Alpaca from `/api/positions/account.status`, audit_log from `mtime` of `data/trade_theses.jsonl`. |
| 4 | **MEDIUM** | Fleet page | API correctly returns `n_vessels: 0` and 0/0/0/0 categories — but the frontend filter chips render `Jones Act/Domestic 5`, `Shadow 5`, `Sanctioned 5`, `Other 5`. Hardcoded `5` doesn't match the API. | Replace the hardcoded count with `categories[key].count` from `/api/fleet/categories`. Also surface an "AISStream not connected" banner on the fleet route while `n_vessels === 0 && last_message_seconds_ago === 0`. |
| 5 | **MEDIUM** | Positions page | `/api/positions/account` returns `buying_power: $200,000`, `cash: $100,000`, `equity: $100,000`, `status: ACTIVE` — but the frontend shows `BUYING POWER $0.00 · EQUITY $0.00 · DAY P&L $0.00`. Frontend either isn't fetching the account endpoint or is rendering the wrong field. | Trace the Positions page data fetch; either it's using `/api/positions` (orders) instead of `/api/positions/account`, or the schema mapping has wrong keys. |
| 6 | **LOW** | `/api/backtest` | `rolling_12m_sharpe` returns a scalar (`6.15`) under a name that suggests a time series. | Either rename to `rolling_12m_sharpe_latest` or return the full series so a trend can be plotted. |
| 7 | **LOW** | `/api/spread` | Does not expose cointegration p-value, half-life, regime tags, or GARCH outputs. They live only inside `thesis.context`. | Add an `/api/diagnostics` endpoint (or extend `/api/spread`) so other surfaces (e.g. macro page) can render those metrics without round-tripping through a thesis generation. |
| 8 | **LOW** | Frontend Data Quality tile | Shows green for yfinance even though the API says amber; shows amber for the rest with no timestamp. The tile is computing status independently of `/api/data-quality`. | Once finding #3 lands, switch the tile to consume `/api/data-quality` directly. Until then, document that the tile colors come from per-payload heuristics, not from the named endpoint. |
| 9 | **LOW** | Backtest defaults vs displayed | Macro-page tile shows Sharpe 1.71 on default params; user-driven backtest with `lookback_days=90, z=2.0` returns Sharpe 4.38. Two different "trustworthy" numbers can confuse a reader. | Add a small caption on the macro tile noting the parameter set being used, e.g. `lookback 365d · entry |z|≥2.0 · since 2021-07`. |

### Read-only audit conclusions

Nothing was modified during this audit. Recommended next move: open GitHub issues for findings #1–#5 (high/medium severity), then triage as separate PRs against the stalled `feat/nextjs-fastapi-stack` integration branch.

---

## Appendix — raw API captures

All saved to `/tmp/oil-audit/` on the audit host:

- `data-quality.json`
- `spread.json` · `cftc.json` · `inventory.json` · `fleet.json`
- `calibration.json` · `build-info.json`
- `thesis-latest.json` · `gen3.log` (SSE generate at 17:21Z) · `regen.log` (SSE regenerate at 17:24Z)
- `backtest.json` (params: z=2.0, lookback=90, start=2024-01-01)
- `openapi.json` (all routes)
- `quality-review-2026-04-27/{home,macro,inventory,track-record,fleet,positions}.png`
