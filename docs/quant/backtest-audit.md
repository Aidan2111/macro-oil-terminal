# Backtest look-ahead audit — issue #94

Sharpe 4.4 / hit rate 90.3% / 31 trades on the published `/api/backtest`
sit ~3 Sharpe above the long-run prior for Brent–WTI mean reversion (the
0.7–1.5 Sharpe band reported by professional desks running the same
trade family on long, OOS samples). A delta that large is more likely a
methodological artefact than a genuine edge. This document records the
audit performed on `quantitative_models.py::compute_spread_zscore` and
`backtest_zscore_meanreversion` against every look-ahead surface listed
in the issue, the bootstrap CIs that now ship on the headline metrics,
and the walk-forward OOS Sharpe used as the second-source reality
check.

## Surfaces audited

### Rolling Z-score (entry decision)

`compute_spread_zscore` lags the rolling window with `shift(1)` before
calling `.rolling(window).mean()` / `.std()`. Mean and std at bar t are
therefore computed from `spread[t-W .. t-1]`, never including `spread[t]`
in their own denominator. The Z numerator (`spread[t] - mean[t-1]`) is a
legitimate at-close signal — every input is known to a trader closing
their book at bar t.

Lock-in tests:

- `tests/unit/test_quantitative_models_shift.py` — four pre-existing
  tests covering rolling mean/std, EWMA `Z_Vol`, the manual-mean
  agreement check, and the early-bar NaN contract.
- `tests/unit/test_backtest_no_lookahead.py` (new, this PR) — explicit
  "transient spike at index N" test phrased verbatim from the issue:
  asserts `Z[t]` for every `t ≤ N` is byte-identical between two
  spread paths that diverge wildly for `t > N`. This is a strict
  causality assertion that would fire on any future regression that
  reintroduces same-bar leakage.

### EWMA volatility (sizing / vol adj)

`Spread_EwmaStd` is computed from a `shift(1)` residual stream
(`(Spread - Spread_Mean).shift(1)`) before being fed to
`.ewm(...).mean()`. The vol estimate at bar t therefore uses residuals
strictly `< t`. Locked in by
`test_ewma_z_vol_at_spike_independent_of_post_spike_prices`.

### Entry / exit prices (transaction surface)

The backtester records `entry_spread = spread[entry_bar]` and
`exit_spread = spread[exit_bar]`. Both are at-bar quantities the
trader observes at close. The legacy "fill at next open" alternative
is documented in the inline comment in `quantitative_models.py:318-322`
as deliberately out of scope for this audit — it would shift entries
and exits by one bar and is its own follow-up issue.

Lock-in test: `test_backtest_entry_price_is_signal_bar_close_not_future`
asserts the recorded entry price equals the spread at the recorded
entry bar (i.e. the test would catch any off-by-one that pulled the
fill from a later bar).

## Bootstrap 95% CIs on the headline metrics

`/api/backtest` now returns a `metric_cis` block alongside every point
estimate, populated by `quantitative_models.bootstrap_metric_cis`
(1000 iid trade-level resamples, 95% percentile CI). The motivation is
the issue's third acceptance criterion: with ~30 trades the headline
Sharpe has a 95% CI on the order of ±2 *under ideal iid assumptions*,
so any analysis that quotes Sharpe alone is overclaiming.

Each CI block is shaped:

```json
{ "point": 4.4, "ci_low": 2.6, "ci_high": 5.7 }
```

Metrics covered: `sharpe`, `hit_rate`, `var_95`, `es_95`,
`max_drawdown_usd`, `total_pnl_usd`. The frontend track-record page
should render the CI envelope as a lighter band around the point
estimate; the existing route consumer already tolerates extra fields.

Block-bootstrap on the underlying spread series (rather than iid trade
resampling) is a future refinement — flagged in the docstring.

## Walk-forward OOS Sharpe

`quantitative_models.walk_forward_oos_backtest` is added in this PR as
the time-aware OOS reality check. The semantics: at each cursor `t`,
test on `(t, t + oos_window_days]` only, advance by
`oos_window_days` so test windows never overlap. The aggregated
per-window stats are returned as a DataFrame.

This is the function to call when the question is "if you had run the
strategy live, what Sharpe would you have realized?" — the existing
`walk_forward_backtest` does a sliding in-sample window and is fine
for parameter-stability diagnostics but not for honest OOS reporting.

## Why the published Sharpe may still be high

After the audit, the Sharpe gap vs the 0.7–1.5 prior plausibly comes
from a combination of:

1. **Cost model still under-charges.** Issue #95 (cost-model calibration
   against real broker fills) is the next Tier 1 item and is expected to
   compress the headline Sharpe materially.
2. **Sample size.** 31 trades is not enough to reject the prior; the new
   bootstrap CIs make this explicit. Issue #103 (regression corpus on
   canonical historical scenarios) and #102 (LLM calibration burn-in)
   address the small-sample problem from a different angle.
3. **Regime conditioning.** The blended number averages an "easy-mode"
   high-vol contango regime against a brutal low-vol backwardation
   regime. Issue #101 (regime-segmented backtest) breaks the headline
   into 4 buckets so the worst-quartile Sharpe is reported alongside
   the blended one.

The backlog items above are filed; this PR closes only the look-ahead
audit and the bootstrap-CI publication that the issue explicitly asked
for.
