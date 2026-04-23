# 05 — Risk-Manager Review (Phase A)

> Author persona: **Senior risk manager, commodities / macro book. 18 years
> across sell-side and a multi-strat. Sign-off authority on position limits,
> stress tests, and stop escalation. I read code looking for the moment a
> PM says "the model told me to" after a $5m day. Questions I ask first:
> where are tail-risk metrics, what caps leverage, what happens on a
> 2020-04-20 negative-WTI print, and what does the book look like when
> correlations go to 1?**

## TL;DR

Trade-level risk plumbing is tidy — VaR-95, ES-95, Sortino, Calmar,
rolling-12m Sharpe all land in `backtest_zscore_meanreversion`
(`quantitative_models.py:279-284, 357-390`) and five guardrail clamps
live in `_apply_guardrails` (`trade_thesis.py:389-469`). That's adult
maturity.

Tail-risk posture is structurally thin: VaR/ES is historical-only on a
per-trade sample that can fall to n < 20; no stress replay of
2020-04-20 / 2022-02 Ukraine / 2014-11 OPEC collapse; no explicit
portfolio leverage cap, no margin model, no "ruin check"; Kelly /
vol-targeting are named in the schema (`trade_thesis.py:164`) but
never computed. Everything below is downstream of those gaps.

---

## Findings — severity ranked

### S1 (Blocker) — Historical-only VaR/ES on a thin sample

**File:** `quantitative_models.py:374-378`.

```python
cutoff_idx = max(0, int(0.05 * len(sorted_pnl)) - 1)
var95 = float(sorted_pnl.iloc[cutoff_idx]) if len(sorted_pnl) else 0.0
es95 = float(sorted_pnl.iloc[: cutoff_idx + 1].mean()) ...
```

Three issues: (a) one method only — desk practice pairs historical with
parametric (Normal or Cornish-Fisher) and flags divergence > 25% as a
fat-tail signal; (b) ES is at 95 rather than the FRTB-2019 standard
97.5 — `tests/unit/test_quantitative_models.py:91-94` bakes in the
`var_95`/`es_95` names; (c) denominator is trade count. With n=10,
`int(0.05*10)-1=-1 → max(0,-1)=0` so VaR-95 collapses to the single
worst trade and ES-95 equals VaR-95. Add a parametric sidecar, move to
ES-97.5, return NaN with caveat when n<30.

### S1 (Blocker) — No stress-test replay of historical regime shocks

**Files:** `quantitative_models.py` (no stress function),
`thesis_context.py:201-257` (no scenario fields).

No replay of 2020-04-20 negative WTI (CLK0 settled −$37.63),
2022-02-24 Ukraine spike (Brent +$8 overnight), or 2014-11 OPEC
collapse. `gross_per_bbl = (s - entry_spread) * position` at
`quantitative_models.py:314` has no bound on `s`, no margin, no forced
liquidation. `walk_forward_backtest` (`quantitative_models.py:424-475`)
is month-stepped so 48h event windows are invisible. `regime_breakdown`
(`quantitative_models.py:525-562`) splits by *rolling-vol median* — a
vol regime, not a crisis regime. Fix: add a `stress_scenarios` list
to `ThesisContext` with PnL impact under each named shock plus a
synthetic "+5σ in 1 bar"; block entry when stress-PnL > 5% of capital.

### S1 (Blocker) — No portfolio leverage cap, no margin model, no ruin check

**Files:** `trade_thesis.py:416-446, 362-380`.

The only cap is `suggested_pct_of_capital ≤ 20.0` (line 421), dropped
to 2% under high-vol (line 440). Missing:

- **Gross vs net leverage.** A 20% long-spread is 40% notional
  (long Brent + short WTI). Tier-3 futures size is emitted at line 378
  without distinguishing gross from net.
- **Margin.** `CL=F` IM is ~$5,500/contract (~5-6% notional at $75 WTI).
  `decorate_thesis_for_execution` (line 328) prints
  `"$1000 per contract per $1 move"` but never checks that suggested
  notional fits within available margin.
- **Ruin check.** At `vol_spread_30d_pct` (`thesis_context.py:230`) of
  30–60% ann., daily 1σ move is 2–4%. 20% notional × 4% = 0.8% equity
  hit — nothing cross-checks against a max-daily-loss policy.

Fix: add `max_gross_leverage` (suggest 1.5×) and `max_net_leverage`
(1.0×) in `_apply_guardrails`, and verify Tier 3 worst-case daily move
≤ capital × `max_daily_loss_pct` before emitting the ticket.

### S2 (High) — Kelly / half-Kelly / vol-targeting named but never computed

**Files:** `trade_thesis.py:164` (schema enum:
`["fixed_fractional", "volatility_scaled", "kelly"]`),
`trade_thesis.py:416-446`, `quantitative_models.py:246-253`.

The LLM can emit `position_sizing.method = "kelly"` and the schema
accepts it, but nowhere does the codebase compute
`kelly = (p*b − q)/b` from `bt_hit_rate` and average win/loss on the
`trades` frame (`quantitative_models.py:317-325`). Similarly
"volatility_scaled" is accepted but no code sizes = target_vol /
realised_vol. Only policy check is the 20% cap — an order of magnitude
above half-Kelly for a hit rate of ~60%. Fix: compute
`bt_kelly_fraction`, `bt_half_kelly_fraction`, thread into
`ThesisContext`, and clamp `suggested_pct_of_capital ≤ half_kelly × 100`
when method is "kelly."

### S2 (High) — Max drawdown is in-sample and never drives de-risking

**File:** `quantitative_models.py:342-345`.

`max_dd` is the backtest's historical peak-to-trough and drives Calmar
at line 372. It is never used as a *control*: `bt_max_drawdown_usd`
lands on `ThesisContext` (`thesis_context.py:213`) but
`_apply_guardrails` (`trade_thesis.py:389-469`) never reads it.
Time-under-water (days in drawdown) is not computed at all. Desk
practice: halve size when live DD > 1× historical max, halt at 1.5×.
Fix: propagate `max_dd_days`; add guardrail
"if suggested size × max DD > 5% of capital → cap size to
5% × capital ÷ max_dd."

### S2 (High) — Correlation-crash scenarios absent

**Files:** `quantitative_models.py` (entire), `thesis_context.py:201-257`
(only `crack_corr_30d`).

No tracking of Brent-WTI vs DXY, vs SPX, or intra-spread correlation
breakdown. During physical stress (hurricane, pipeline rupture) Brent
and WTI decorrelate for hours-to-days — the 90d rolling std
(`quantitative_models.py:51-52`) doesn't detect this because it's on
the *level*, not on the *correlation*. Fix: add
`spread_vs_dxy_corr_30d` and `spread_vs_spx_corr_30d`; flag when any
correlation is > 2σ from 1y mean and clamp size to 5%.

### S2 (High) — Liquidity assumptions in the backtest are literally zero

**File:** `quantitative_models.py:248-253, 315-317`.

`slippage_per_bbl: float = 0.0, commission_per_trade: float = 0.0`.
All tail-risk metrics (VaR-95, ES-95, max DD, Sortino) are computed
gross-of-cost. Slippage evaporates precisely when you need to exit
(2020-04-20: reportedly 5–15× normal). `monte_carlo_entry_noise`
(line 481) perturbs only `entry_z` and keeps slippage = 0. Fix:
sample slippage from a LogNormal (σ=0.5, mean = normal × 3) in the
MC, report ES-97.5 under stress-liquidity explicitly.

### S2 (High) — Stretch bands don't map to tail-risk regimes

**File:** `language.py:200-221`.

```
< 0.7 Calm | < 1.3 Normal | < 2.3 Stretched | < 3.2 Very | ≥3.2 Extreme
```

Bands are sigma-count only. Under Normal, |Z|≥3.2 is ~0.14% (1 in
700 days); empirically on Brent-WTI it's ~2% — "Extreme" under-conveys
frequency. Worse, bands don't flip with `vol_spread_1y_percentile`
(`thesis_context.py:231`): a Z=2.4 in low-vol is genuinely unusual,
in high-vol it's monthly — same label. The headline builder reads
`describe_stretch` at `trade_thesis.py:932` so a retail user sees
"stretched" without regime context. Fix: make thresholds
regime-conditional and map each band to a VaR percentile.

### S3 (Medium) — Sortino / Calmar can return `float("inf")`

**File:** `quantitative_models.py:360-364, 372`.

`sortino = ... float("inf") if pnl_series.mean() > 0 else 0.0` — goes
infinite exactly when the sample has no losers yet, which is when a
PM is most tempted to size up. Same at line 372 when `max_dd == 0`.
Inf in the audit JSONL (`trade_thesis.py:725-743`) will break any
downstream histogram. Return `NaN` with a `metric_defined: bool`
companion.

### S3 (Medium) — "Rolling 12m Sharpe" is trades-based, not calendar-based

**File:** `quantitative_models.py:380-390`.

`w = max(3, int(round(trades_per_year)))` — a rolling *N-trade* Sharpe
evaluated at trade exits. In a slow regime (2 trades/yr) `w=3` (clamped)
and the metric is a 3-trade noise; in a frenzy (40/yr) it's a 40-trade
estimate. The key name `"rolling_12m_sharpe"` (lines 284, 407) promises
calendar time. Rename to `rolling_ntrade_sharpe` and also expose a
true calendar-window Sharpe on daily mark-to-market PnL.

### S3 (Medium) — Half-life checklist item is a placeholder string

**File:** `trade_thesis.py:316-318`.

`"I understand the implied half-life is ~N days."` — the literal
`~N` is rendered; `coint_half_life_days` exists on the context
(`thesis_context.py:239-241`) but is never substituted. Users
rubber-stamp without reading the value. If half-life = 40d and the
user's stop horizon = 5d, the trade is closed on noise. Fix:
`f"...~{ctx.coint_half_life_days:.0f} days."` and N/A when None.

### S3 (Medium) — No circuit-breaker on consecutive losses

**Files:** `quantitative_models.py:296-331`, `trade_thesis.py:389-469`.

No longest-losing-streak, no worst 5-trade rolling PnL, no "days since
last win." `_apply_guardrails` uses *overall* `bt_hit_rate` (line 405);
a strategy that won 80% over 5 years but lost the last 6 straight
still scores 0.73 and is not clamped. Fix: compute rolling-20-trade
hit rate and clamp to flat when < 40%.

### S4 (Low) — `max_drawdown_usd` is dollars, not %

**Files:** `quantitative_models.py:345`, `trade_thesis.py:520`.

$50k DD on $10k notional = catastrophic; on $10m notional = trivial.
The rule-based thesis prints the raw dollar figure without context.
Also carry `max_drawdown_pct = max_dd_usd / (notional_bbls × avg_spread)`.

---

## What's right, keep it

- Five-clamp `_apply_guardrails` (`trade_thesis.py:389-469`): inventory-missing
  → flat, weak-backtest → conviction cap, 20% sizing cap, high-vol 2%
  clamp, coint-broken conviction cap. Real discipline.
- VaR/ES *present at all* (`quantitative_models.py:374-378`) — most
  research dashboards stop at Sharpe.
- `test_backtest_risk_metrics_present`
  (`tests/unit/test_quantitative_models.py:91-94`) enforces the risk
  contract in CI; `test_backtest_empty_risk_metrics_zero`
  (lines 110-115) covers the degenerate zero-trade case.
- Vol-regime clamp (`trade_thesis.py:428-446`) connects tail-risk
  conditions to sizing — the right pattern to extend.
- `monte_carlo_entry_noise` (`quantitative_models.py:481-519`) —
  parameter-sensitivity at all is rare at this maturity.

## Bottom line

Trade-level risk metrics are defensible for research. Tail-risk and
portfolio-level posture is not yet at sign-off level. Before Phase B:
parametric VaR sidecar + ES-97.5, historical-shock replay, and
leverage/margin/ruin checks. S2 items are credibility-of-risk-tile
issues — they make the metrics sound more informative than they are.

— *Risk Manager, 2026-04-23.*
