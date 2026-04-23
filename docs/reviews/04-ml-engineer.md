# ML-engineer review — macro-oil-terminal (Phase A, persona 4)

> Reviewer persona: **"R. Patel" — senior ML engineer, 10y productionising
> forecasting and decision models (credit, fraud, ads). Treats every fitted
> coefficient and every LLM confidence field as a model artifact subject to
> train/test hygiene, calibration, drift monitoring, and reproducibility
> contracts. No free passes for "it's just a regression."**

## TL;DR

There are two models in this codebase even though nothing is deep-learned:
(1) the `LinearRegression` fit in `forecast_depletion`
(`quantitative_models.py:120`) and (2) the Z-score + LLM+guardrails pipeline
that issues a *stance*, *conviction*, and *size* (`trade_thesis.py:887-959`,
`quantitative_models.py:246-418`). Both suffer from classic ML-hygiene gaps:
**in-sample evaluation reported as if it were predictive, no calibration of
the confidence scalar, non-stationary features fed to rolling statistics
without a stationarity check, and no drift/degradation alarm.** The Monte
Carlo over `entry_z` (`quantitative_models.py:481-519`) and the walk-forward
(`quantitative_models.py:424-475`) are the right instincts but their results
are not fed back into the thesis pipeline, so the live decision never sees
whether its own parameters are stable.

## Methodology

Read `quantitative_models.py` end-to-end. Read `trade_thesis.py` with a focus
on the guardrail/confidence path. Read `thesis_context.py` to trace how
features are assembled from providers. Spot-checked `data_ingestion.py` and
the unit tests under `tests/unit/`. Looked for: train/test discipline, data
leakage, hyperparameter sensitivity, calibration, reproducibility, drift,
stationarity, backtest-vs-live parity.

## Findings — severity ranked

### S1 — Critical

**F1. Depletion regression is evaluated in-sample and reported as predictive.**
`forecast_depletion` fits `LinearRegression` on the trailing
`lookback_weeks` (default 4) points and then reports `r_squared` from
`model.score(x_days, y)` on *the same* points
(`quantitative_models.py:120-127`). With `n=4` and `p=1`, in-sample R² is
almost meaningless and will typically look ≥0.8 on a monotonic segment.
There is no holdout, no CV, no prediction-interval, no out-of-sample check
against, say, the next 4 weeks once they arrive. The `projected_floor_date`
(`quantitative_models.py:132-137`) is then extrapolated up to **3 years
forward** (`horizon_end = t0 + 365*3` at line 142) from a 4-point fit — a
textbook extrapolation failure. Either (a) add leave-one-out MAE across the
last K windows and surface it to the UI, or (b) replace with an ARIMA/ETS
with a proper prediction interval and refuse to project past ~horizon =
lookback.

**F2. Backtest hit-rate used as a calibration prior is 100% in-sample.**
The guardrail at `trade_thesis.py:405-414` clamps LLM conviction to 5 when
`bt_hit_rate < 0.55`. But `bt_hit_rate` comes from
`backtest_zscore_meanreversion` (`quantitative_models.py:246-418`), which
runs on the **entire** `spread_df` — the same window whose current Z-score
is being used to pick today's stance (`app.py:441-444`). The hit-rate
therefore includes the trade we are about to put on. This is the canonical
look-ahead-bias for rule-based strats: it overstates realised edge and
gives the LLM a falsely-confident prior. Fix: compute
`bt_hit_rate` on a strict lagged window (e.g. data older than
`now - avg_hold_days * k`) or feed the walk-forward last-fold hit-rate
(`quantitative_models.py:466-472`) instead.

**F3. `current_z` contains a rolling stat that leaks future info at the
edges.** `compute_spread_zscore` uses
`rolling(window=90, min_periods=max(5, window//3)).mean()` and `std()`
(`quantitative_models.py:51-52`). By itself that is fine (past-only). But
the **EWMA residual variance** at `quantitative_models.py:60-62` uses
`Spread - Spread_Mean`, where `Spread_Mean` is the trailing 90d mean — the
*current* day's spread is differenced against a window **that includes
itself**. That produces a tiny self-similarity bias in `Z_Vol`. At n=90 the
bias is small, but on the first ~30 rows (`min_periods=30`) it is
material. Either shift the rolling mean (`.shift(1)`) or document that the
first warm-up observations are unsafe for backtest entry logic.

### S2 — High

**F4. Hyperparameter sensitivity of the Z-score window is never measured.**
The 90d window is hardcoded at `app.py:432` (`_spread_cached(_fp(prices),
90)`), exposed neither to the user nor to the thesis context. The Monte
Carlo (`quantitative_models.py:481-519`) wiggles `entry_z` but not
`window`. A 60d vs 90d vs 120d window routinely flips stance on the
Brent-WTI pair (different mean-reversion half-life regimes). At minimum:
run `walk_forward_backtest` across `window ∈ {30, 60, 90, 120, 180}` and
publish the Sharpe surface; refuse to issue `|conviction| > 5` if the
stance flips on a ±30d perturbation.

**F5. LLM `conviction_0_to_10` is never calibrated against realised hit
rate.** The JSON schema at `trade_thesis.py:137` defines
`conviction_0_to_10` and the audit log at `trade_thesis.py:728-743` captures
every thesis, but nothing compares `conviction` buckets to realised outcome
(did the spread actually mean-revert inside `time_horizon_days`?). Without
reliability-diagram / Brier-score tracking, the conviction scalar is
cosmetic. Add a nightly job that reads `data/trade_theses.jsonl`, joins on
realised spread at `generated_at + time_horizon_days`, and emits an
ECE/Brier-score per conviction bucket. Surface the last 90d ECE on the
dashboard as a health tile.

**F6. No drift monitoring on the input feature distribution.** None of the
features assembled in `thesis_context.build_context`
(`thesis_context.py:87-257`) are checked for distributional shift vs
training/baseline. `vol_spread_1y_percentile` is a self-referential stat —
it's 50 by construction if the last year is representative, but if the
regime has shifted, the percentile still reads "normal." Add
Kolmogorov-Smirnov or Population-Stability-Index tracking on
`current_z`, `vol_spread_30d_pct`, `inventory_4w_slope_bbls_per_day`,
`cftc_mm_net` vs a 3y rolling baseline. A PSI > 0.25 should force a data
caveat into the thesis.

**F7. Backtest Sharpe uses `sqrt(365/mean_hold_days)` annualisation — a
brittle proxy.** `quantitative_models.py:352-355` annualises the Sharpe
via `sqrt(365/mean_hold_days)` where trades are irregularly spaced. When
`mean_hold_days` is small (strategy triggers often) this inflates Sharpe
by a factor of 10x+. A regime with many 1-day round-trips reports an
implausible Sharpe that then feeds `bt_sharpe` into `ThesisContext`
(`thesis_context.py:214`). Swap for daily-return Sharpe on the equity
curve, or gate on `n_trades < 20 → NaN`.

### S3 — Medium

**F8. Stationarity of the spread is assumed, not tested, before
mean-reversion stats are reported.** The whole
`backtest_zscore_meanreversion` path
(`quantitative_models.py:246-418`) treats `Spread = Brent - WTI` as
stationary. The codebase *does* ship a cointegration test
(referenced in `_apply_guardrails` at `trade_thesis.py:449-464`) but the
backtest itself runs unconditionally and its metrics populate
`ThesisContext.bt_*` regardless. If `coint_verdict == "not_cointegrated"`,
`bt_hit_rate` etc. should be masked to NaN, not just caveated. Otherwise
the LLM sees "hit rate 62%" on a period the test just told us was
non-stationary.

**F9. Reproducibility is partial: seed in Monte Carlo, no seed on LLM.**
Good: `monte_carlo_entry_noise` takes a `seed=7` default
(`quantitative_models.py:489,500`) and AIS snapshot uses a fixed seed
(`data_ingestion.py:123`). Bad: `_call_azure_openai`
(`trade_thesis.py:571-719`) sets `temperature=0.2`
(`trade_thesis.py:648`) but does not pin a `seed` — Azure OpenAI
supports `seed` for deterministic sampling. Without it, two identical
`ThesisContext.fingerprint()` inputs can return different stances. That
breaks the audit contract: the fingerprint claims "same inputs = same
thesis" but the LLM is free to flip. Pass
`seed=hash(ctx.fingerprint()) & 0xFFFFFFFF` into the API call.

**F10. Feature engineering inputs are not stationary-differenced.** The
LLM receives raw price levels (`latest_brent`, `latest_wti`,
`inventory_current_bbls`) and pre-computed rolling stats, but never
log-returns or first-differences
(`thesis_context.py:102-109`, `201-257`). Raw prices are I(1). LLMs pattern
match on levels more than changes; feeding in absolute $82.34 vs $79.10
biases the model toward "these look close to historical highs" reasoning
rather than evaluating the actual *dislocation*. Add
`brent_log_ret_1d`, `wti_log_ret_1d`, `inv_wow_pct_change` to
`ThesisContext` as stationary companions.

**F11. Backtest-vs-live parity gap: transaction costs live in the
backtest but not in sizing.** `backtest_zscore_meanreversion` accepts
`slippage_per_bbl` and `commission_per_trade`
(`quantitative_models.py:251-252`). The app passes user values in
(`app.py:441-444`). But `_apply_guardrails` sizes purely off
`suggested_pct_of_capital` and vol percentile
(`trade_thesis.py:416-446`) — it never penalises conviction when
implied post-cost edge is negative. A trade with a 55% win rate and $0.30
per-bbl edge breaks even under $0.15/bbl round-trip slippage; the
guardrail has no knowledge of that. Add a post-cost expected-edge check:
if `bt_avg_pnl_per_bbl - 2*slippage_per_bbl < 0`, clamp conviction ≤ 3.

### S4 — Low

**F12. No model card / no versioning of the rule-based fallback.**
`_rule_based_fallback` (`trade_thesis.py:475-542`) is the model that runs
whenever Azure is down. It has a specific formula
(`conviction = |z|/thr * 6.0` at line 487) that has never been
backtested, has no version string in the audit log, and is logged under
`source="rule-based (fallback)"` (`trade_thesis.py:904,918-920`). If the
Azure endpoint has a bad week, every thesis in the audit log comes from an
unversioned rule that could be changed tomorrow and invalidate the whole
backtest. Add a `fallback_version="1.0.0"` constant and persist it on
every fallback record; bump on every change.

## Recommended next actions (engineer-hours)

1. (S1) Replace in-sample `r_squared` with leave-one-out MAE + prediction
   interval; cap projection horizon at `lookback_weeks * 4`. **~3h**.
2. (S1) Fix backtest look-ahead by feeding walk-forward last-fold hit-rate
   into `ThesisContext.bt_hit_rate`. **~2h**.
3. (S2) Nightly calibration job: reliability diagram + Brier score from
   `data/trade_theses.jsonl` joined with realised spread; surface ECE
   tile. **~6h**.
4. (S2) Window-sensitivity sweep on `compute_spread_zscore` window; block
   high conviction when stance is not invariant to ±30d. **~3h**.
5. (S3) Pin `seed` on Azure OpenAI calls to restore fingerprint→thesis
   determinism. **~30min**.
6. (S3) PSI drift tile on the 5-6 load-bearing features. **~4h**.

Word count: ~1,180.
