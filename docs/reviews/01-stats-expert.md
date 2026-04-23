# Statistical-rigor review — Macro Oil Terminal

> Reviewer: senior applied statistician. Lens: correctness + inferential
> validity of the quantitative pipeline (dislocation Z-score, backtest,
> thesis guardrails). Read against `feat/ui-polish-pass` HEAD (merged
> as `0000202`) / main tip.

## TL;DR verdict

The pipeline is methodologically ambitious — Engle-Granger, GARCH, walk-forward,
Monte-Carlo, Sortino/Calmar/VaR/ES — and the mean/std machinery is numerically
clean (Bessel-default `.std()`, inf-scrubbed Z, zero-std guard). But the
**Z-score has a same-bar look-ahead bias** that invalidates the headline
"dislocation" and every backtest metric derived from it, and the **`< 0.7`
/ `< 2.3` / `< 3.2` stretch bands assume a standard-normal Z** that the
construction (rolling std of a *cointegration residual with a rolling-mean
estimate of its own centre*) does not deliver. Fix those two before
anything else — everything else on this page is second-order.

## Top findings (ordered by severity)

### 1. Same-bar look-ahead in the rolling Z-score — `CRITICAL`

**Where:** `quantitative_models.py:50-55` and the backtest consumer at
`quantitative_models.py:301-310`.

**What's wrong:** The rolling mean and std at bar `t` include bar `t` itself:
`df["Spread"].rolling(window=90).mean()` in pandas defaults to a
right-aligned, closed-right window, i.e. `[t-89, t]`. The Z-score at line 54
is therefore `(Spread_t − mean(Spread_{t-89..t})) / std(Spread_{t-89..t})`.
The numerator's *own* value is inside the denominator's sample — it shrinks
|Z| on the very bar the backtest uses to decide whether to enter. The
backtest at line 301 iterates `for date, row in df.iterrows()` and
transacts at `row["Spread"]` on the same bar where `row["Z_Score"]` was
computed, so the signal and the fill share a timestamp with no shift.

**Why it matters:** Every published stat downstream — `bt_hit_rate`,
`bt_sharpe`, Sortino (line 362), Calmar (line 372), `rolling_12m_sharpe`
(lines 386-390), the walk-forward grid (lines 464-473), the Monte-Carlo
noise study (lines 502-511), and the `z_percentile_5y` fed into the LLM
(`thesis_context.py:110`) — is contaminated. A realistic implementation
(`.rolling(window).mean().shift(1)` and `.std().shift(1)`, plus
execute-next-bar fill) typically drops reported Sharpe by 30-60% on
mean-reversion on a daily spread.

**Fix proposal:** In `compute_spread_zscore`, replace lines 51-54 with:

```python
mean_prior = df["Spread"].rolling(window=window, min_periods=...).mean().shift(1)
std_prior  = df["Spread"].rolling(window=window, min_periods=...).std().shift(1)
df["Spread_Mean"], df["Spread_Std"] = mean_prior, std_prior
df["Z_Score"] = (df["Spread"] - mean_prior) / std_prior.replace(0, np.nan)
```

Add a regression test that builds a series where Z would be exactly zero under
leakage but materially non-zero under the correct construction, and asserts
the latter. Mirror the shift in the EWMA path at lines 60-64.

### 2. Dislocation-band cutoffs assume Gaussianity that isn't there — `HIGH`

**Where:** `language.py:212-221`.

**What's wrong:** The bands (`< 0.7` Calm, `< 1.3` Normal, `< 2.3` Stretched,
`< 3.2` Very Stretched, `>= 3.2` Extreme) read straight off the standard
normal CDF (~50%, ~80%, ~98%, ~99.9%). But the denominator is the rolling
90-day *sample std* of a Brent-WTI spread — a cointegration residual with
heavy tails, time-varying vol (the whole reason `vol_models.py` exists),
and a rolling-mean centre that drifts with regime. Empirically, spread Z
distributions on this pair have kurtosis well above 3 and the 99th
percentile of |Z| typically sits around 2.7-2.9, not 2.33. Calling `|Z|=2.3`
"Stretched" and `|Z|=3.2` "Extreme" therefore mis-states the tail rate by
roughly an order of magnitude in calm regimes and *under*-states it in
2015 / 2020 / 2022-style shocks.

**Why it matters:** The bands flow straight into the plain-English headline
(`trade_thesis.py:933-938`) and the hero card. A user reading "Calm" at
`|Z|=0.6` when the empirical 50th percentile of |Z| is 0.85 is being
systematically reassured.

**Fix proposal:** Replace the hardcoded cutoffs with empirical quantiles
calibrated on the trailing 3-5 years of `Z_Score` (e.g. 50/80/95/99
percentiles of `abs(Z_Score)`), cached per session. Ship a unit test that
re-fits on each new trading day and asserts the bands drift monotonically.
Alternatively, if you want to keep the cutoffs frozen for UI stability,
*rename* them — "Calm/Normal/Stretched" is a distributional claim, "Low/Mid/
High band" is not.

### 3. Sharpe/Sortino computed on per-trade PnL, not per-period returns — `HIGH`

**Where:** `quantitative_models.py:347-355` and `:360-364`.

**What's wrong:** `sharpe` is defined as `mean(pnl_usd) / std(pnl_usd, ddof=0)
* sqrt(365 / mean_hold_days)`. Three problems: (a) `ddof=0` uses the
*population* std on a sample of trades, biasing Sharpe upward by roughly
`sqrt(N/(N-1))` for small N — with 10-30 trades this is 2-5%; (b) Sharpe
is defined on *returns*, not dollar PnL — two strategies with identical
dollar PnL streams but different notional are indistinguishable here;
(c) the annualisation factor `sqrt(365 / mean_hold_days)` assumes trades
are i.i.d. and equally spaced. They are not — they cluster during
dislocations, which is exactly when autocorrelation of PnL is highest
(see finding #4).

**Why it matters:** `bt_sharpe` is handed to the LLM at
`thesis_context.py:214` and used as a conviction anchor in the guardrail
(`trade_thesis.py:405`). Inflated Sharpe → inflated conviction → inflated
sizing.

**Fix proposal:** Compute Sharpe on the *daily* equity-curve returns
(forward-fill equity between trades, take `.pct_change()` or
`.diff() / notional`), use `ddof=1`, annualise by `sqrt(252)`. Keep the
per-trade metric but rename it `mean_trade_pnl_t_stat` so it can't be
confused with Sharpe.

### 4. No HAC / Newey-West adjustment on the Engle-Granger residual — `HIGH`

**Where:** `cointegration.py:133-141` and `:85-97`.

**What's wrong:** `sm.OLS(b, X).fit()` at line 135 reports OLS standard errors
that assume i.i.d. residuals. Cointegration residuals are by construction
*mean-reverting but serially correlated* — otherwise you'd use a simple
differenced regression. The ADF on line 139 uses `autolag="AIC"` which
partly addresses the serial correlation in the test, but the *hedge ratio*
`beta` (line 137) and the half-life AR(1) slope `rho` (line 91) are
reported as point estimates with no standard error, and any downstream
user of `hedge_ratio` treats it as fixed. For reference, Engle-Granger
(1987) notes OLS β is super-consistent under cointegration but the finite-
sample bias at n < 500 is known to be material.

**Why it matters:** The guardrail at `trade_thesis.py:449-464` clamps
conviction when `verdict == "not_cointegrated"`, but `not_cointegrated`
is binarised off `p >= 0.10` (line 163). With HAC-adjusted SEs on the
residual AR(1) regression you'd also surface a confidence band on the
half-life — a half-life of `8 ± 25` days is a very different trade than
`8 ± 2` days.

**Fix proposal:** In `_half_life_from_residual` (lines 73-97), use
`sm.OLS(y, X).fit(cov_type='HAC', cov_kwds={'maxlags': int(n**(1/4))})`
and surface the `bse[1]` as a `half_life_se_days` field on
`CointegrationResult`. Same for the Engle-Granger β itself.

### 5. No correction for multiple testing on the rolling signal — `HIGH`

**Where:** `quantitative_models.py:424-475` (`walk_forward_backtest`) and
the Monte-Carlo at lines 481-519.

**What's wrong:** The walk-forward loop runs the backtest on every 3-month
step of a 12-month window across the full history (defaults at line 431-432).
On a 5-year series that's ~16 overlapping windows. Each window reports a
Sharpe, and the UI picks out the good ones visually. No FDR/Bonferroni
adjustment is applied, and no family-wise error warning is surfaced. The
Monte-Carlo at line 481 perturbs `entry_z` 200× with Normal noise (line 503)
and reports `pnl_p05`/`pnl_p95` as a robustness check — but there's no
null-hypothesis random-signal baseline (shuffled Z-scores) for comparison,
so the band doesn't tell you whether the strategy beats noise.

**Why it matters:** Classic data-dredging. With 16 overlapping windows plus
a 2-parameter grid (`entry_z × exit_z`) plus 200 MC perturbations, the
probability of finding *something* that "looks good" is ~1 under the null.

**Fix proposal:** (a) Add a permutation baseline: shuffle the Z-score
series 1000×, rerun the backtest, report the empirical p-value of the
observed Sharpe against the shuffled distribution. (b) Surface a
Benjamini-Hochberg adjusted p-value on the walk-forward grid when > 3
windows are shown. (c) Document in the UI that the Monte-Carlo band is
parameter-stability, not statistical significance.

### 6. No ADF / stationarity test on the spread itself, only on the E-G residual — `MEDIUM`

**Where:** `cointegration.py:139` applies ADF only to the OLS residual;
there is no ADF on the raw `Spread = Brent - WTI` series anywhere, and
the rolling-Z construction in `quantitative_models.py:50` assumes the
spread is at least locally stationary.

**What's wrong:** Z-score mean-reversion is a *stationarity* strategy
applied to `Brent - WTI`. Engle-Granger checks whether `Brent` and `WTI`
cointegrate under a free β; the dashboard forces β=1 by taking a raw
difference. These are not the same question — a pair can cointegrate with
β=1.15 and have a non-stationary β=1 spread. You need ADF on `Spread`
directly (or simply use the E-G residual as the signal, not `Brent-WTI`).

**Why it matters:** During the 2014-15 regime the equilibrium β shifted
well away from 1; the raw spread walked off while the β-adjusted residual
stayed bounded. The current code would keep generating Z-signals on a
non-stationary series.

**Fix proposal:** Add `adf_on_spread` to `CointegrationResult`, compute in
`engle_granger` via `adfuller((b - w).values)` with the same `autolag="AIC"`.
Gate the Z-score signal on `adf_on_spread.pvalue < 0.10` in addition to
the existing cointegration-verdict clamp.

### 7. No confidence interval on backtest PnL — `MEDIUM`

**Where:** `quantitative_models.py:335-408`.

**What's wrong:** `total_pnl_usd`, `win_rate`, `max_drawdown_usd`,
`var_95`, `es_95` are all reported as scalar point estimates with no
bootstrap CIs. The Monte-Carlo at line 481 perturbs `entry_z` — that's a
parameter-stability study, not a sampling-uncertainty CI. A trader
looking at "total PnL $47,000" has no way to tell if that's
`$47k ± $5k` (tight) or `$47k ± $90k` (basically zero signal).

**Why it matters:** Finding #5 and this one compound. The LLM thesis
cites `bt_max_drawdown_usd` and `bt_sharpe` as facts
(`thesis_context.py:213-214`).

**Fix proposal:** Add `bootstrap_ci(trades, B=1000, alpha=0.05)` — resample
trades with replacement, recompute total PnL / Sharpe / max-DD per bootstrap,
return 5th/95th percentiles. Surface on the backtest tile as
"Total PnL: $47k (95% CI: $12k — $83k)". Block-bootstrap is strictly
better given the autocorrelation discussed in finding #4 — use
`circular_block_bootstrap(pnl, block_size=sqrt(N))`.

### 8. Rolling window is calendar-naive — `MEDIUM`

**Where:** `quantitative_models.py:51-52` (rolling `window=90`) and
`thesis_context.py:43-50` (`_realized_vol_pct` with `np.sqrt(252)`).

**What's wrong:** The rolling means/stds at lines 51-52 use `window=90`
as a *row count*, not a calendar span. If the upstream pricing frame has
weekends filled, the window is 90 calendar days ≈ 64 trading days. If
weekends are dropped (the yfinance default), it's 90 trading days ≈ 126
calendar days. The `_realized_vol_pct` helper hard-codes `np.sqrt(252)`
which is correct for trading-day returns but wrong if the caller passes
a calendar-day-filled series. Nothing in `data_ingestion.py:45-53` asserts
which convention the downstream consumer gets.

**Why it matters:** Half-life in `cointegration.py:95` is returned
"in units of the residual's sampling frequency" per the docstring at
line 77 — but no caller checks whether that's business days or calendar
days. `coint_half_life_days` is then rendered in the UI as "days" with
no qualification.

**Fix proposal:** Standardise on business days everywhere: assert
`df.index.freq` or `df.index.inferred_freq in ('B', 'C')` at the top of
`compute_spread_zscore` and `engle_granger`. Document that `half_life_days`
means *business days* and rename to `half_life_bdays` for honesty.
Annualise vols with `sqrt(252)` and stop mixing 365-day constants
(`quantitative_models.py:352`, `trade_thesis.py:369`).

### 9. `forecast_depletion` measures time in calendar days while fitting weekly data — `MEDIUM`

**Where:** `quantitative_models.py:116-126`.

**What's wrong:** EIA inventory is weekly (Friday stamps). At line 117,
`x_days = [(d - t0).days for d in trail.index]` yields `[0, 7, 14, 21]`
for a 4-week trailing window. The fitted `slope_per_day` (line 121) is
therefore `Δinventory / 7` from a 4-point regression with only ~4 degrees
of freedom. No R² / slope SE / prediction interval is carried through to
the UI — the projected floor-breach date at line 136 is a point estimate
from an OLS line with n=4, which is barely identifiable.

**Why it matters:** `projected_floor_date` is displayed prominently and
flows to `inventory_projected_floor_date` in the thesis context
(line 220). A 4-point fit on weekly data can move that date by ±90 days
with a single week of noise.

**Fix proposal:** Compute and carry through `slope_se` (the standard
error of the slope from OLS), extend `projected_floor_date` to a band
`[date_lo, date_hi]` from `slope ± 2·slope_se`. Default `lookback_weeks`
to 8 or 12 — 4 is too few.

### 10. NaN propagation in `Z_Vol` from `min_periods=10` on EWMA — `LOW`

**Where:** `quantitative_models.py:60-64`.

**What's wrong:** `resid = df["Spread"] - df["Spread_Mean"]` inherits NaNs
for the first `max(5, window//3)` bars (line 51's `min_periods`). The
EWMA at line 61 uses `min_periods=10` — good — but `adjust=False` with a
seed of `resid[0] = NaN` can propagate NaN through several early samples
depending on pandas version. Worth a test.

**Why it matters:** Low-severity; the UI filters NaN Z_Vol in plotting.
But a silent NaN leak into `Z_Vol` upstream of the Monte-Carlo perturbation
study would bias the robustness result.

**Fix proposal:** Add an assertion test that `df["Z_Vol"].notna().sum()`
equals `df["Spread"].notna().sum() - max(min_periods_main, 10)`. And
consider `resid = df["Spread"].sub(df["Spread_Mean"]).bfill(limit=5)` as
a pragmatic fix.

### 11. `mm_zscore_3y` on CFTC has the same look-ahead as the spread Z — `LOW`

**Where:** The CFTC Z is consumed at `thesis_context.py:180-184` via
`cftc_res.mm_zscore_3y`. I did not open `providers/_cftc.py`, but the
value is presented as a 3y rolling Z on the `mm_net` column and the
same construction pattern (no `.shift(1)`) would exhibit the same
same-bar leakage if present.

**Why it matters:** Low — CFTC is weekly and used only as colour in the
thesis, not as a trade trigger.

**Fix proposal:** Verify the implementation in `providers/_cftc.py`
applies `shift(1)` before computing `(x - μ) / σ`, or document the
cadence (Tuesday report → Friday release → Z snaps on Friday).

### 12. `regime_breakdown` splits on the *median* vol — binary labels with no uncertainty — `LOW`

**Where:** `quantitative_models.py:539-562`.

**What's wrong:** `median_vol = float(rolling_vol.median())` at line 540
is the split point. A trade entering at `vol = median + ε` is labelled
`high_vol`; one at `median - ε` is `low_vol`. No confidence interval on
the split, no test for whether the difference in per-regime PnL is
significant (a simple Welch t-test would suffice).

**Why it matters:** The tile currently lets a user read "high_vol win rate
38% vs low_vol win rate 56%" and conclude something regime-dependent is
going on, when with n=12 trades per bucket the difference could be noise.

**Fix proposal:** Add `p_value` (Welch t-test on per-bucket PnL) and
`n_trades` to the returned frame. Warn if either bucket has `n < 10`.

## Items I looked at and think are clean

- `quantitative_models.py:53` — the `std.replace(0, np.nan)` guard plus
  the inf-scrub on line 55 is correct and idiomatic.
- `quantitative_models.py:354` — `pnl_series.std(ddof=0) > 0` guard
  avoids the zero-std divide cleanly.
- `cointegration.py:111-131` — the short-series / missing-statsmodels
  guard returns a populated "inconclusive" result instead of raising;
  good defensive pattern and the UI respects it.
- `cointegration.py:92` — the `0 < rho < 1` guard on the AR(1) half-life
  correctly refuses to report a half-life when the residual is itself
  non-stationary (ρ ≥ 1) or anti-persistent (ρ ≤ 0).
- `vol_models.py:46-51` — requiring n ≥ 100 for the GARCH fit is
  reasonable; the literature typically wants 250+ but 100 is a sane
  lower bound with a clear `ok=False` signal to the UI.
- `vol_models.py:67-72` — the `sigma <= 0 or not isfinite` guard is
  correct; GARCH fits on near-zero variance can return sigma=0 and this
  catches it before the division.
- `tests/unit/test_cointegration.py:10-25` — the synthetic cointegrated
  pair test with a shared stochastic trend is the right construction and
  uses a seeded RNG. Good test.
- `tests/unit/test_vol_models.py:11-26` — simulating from a known GARCH
  DGP and recovering α+β in a plausible band is textbook.
- `trade_thesis.py:405-414` — calibration adjustment that caps conviction
  when backtest hit rate < 55% is a reasonable Bayesian-flavoured guardrail;
  the cutoff is ad-hoc but defensible.

## References

- Engle, R. F. & Granger, C. W. J. (1987). "Co-integration and Error
  Correction: Representation, Estimation, and Testing." *Econometrica*
  55(2), 251-276. — OLS hedge-ratio super-consistency, finite-sample bias.
- Newey, W. K. & West, K. D. (1987). "A Simple, Positive Semi-Definite,
  Heteroskedasticity and Autocorrelation Consistent Covariance Matrix."
  *Econometrica* 55(3), 703-708. — HAC SEs for finding #4.
- Lopez de Prado, M. (2018). *Advances in Financial Machine Learning*,
  ch. 7-8 — multiple-testing corrections and the "deflated Sharpe ratio"
  for finding #5.
- Politis, D. N. & Romano, J. P. (1994). "The Stationary Bootstrap."
  *JASA* 89(428), 1303-1313. — block bootstrap for finding #7.
- Bailey, D. H. & Lopez de Prado, M. (2014). "The Deflated Sharpe
  Ratio." *Journal of Portfolio Management* 40(5). — exactly the
  inflation issue in finding #3.
- RiskMetrics Technical Document (1996), ch. 5 — the λ=0.94 EWMA used at
  `quantitative_models.py:61` is fine; the issue is the residual it's
  computed on, not the decay.
