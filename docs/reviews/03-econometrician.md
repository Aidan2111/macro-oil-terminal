# 03 — Econometrician Review (Phase A)

> Author persona: **time-series econometrician — ADF / KPSS / Johansen /
> VECM / MSAR in my sleep. Reading this product as a claim about the
> long-run equilibrium of Brent vs WTI, not as a UI.**

## TL;DR

The econometric **scaffolding** is clean and defensive — dataclasses are
well-typed, every helper has a graceful-degradation path, and the
cointegration / GARCH / Z-score tests use credible synthetic generators.
But the econometric **depth** is shallower than the docstrings imply.
The Z-score that drives every trading decision is a flat-spread,
fixed-window, rolling-std object. Two alternative vol estimators (EWMA,
GARCH) are computed and then thrown away. Johansen, VECM, Granger,
impulse-response, and Markov-switching are absent. The half-life is
displayed but never enforced. The single highest-leverage fix is wiring
`coint_half_life_days` and a β-adjusted residual into the backtest and
the thesis horizon — that alone closes the gap between what the UI
claims and what the signal does.

---

## Findings — severity ranked

### S1 (Blocker) — GARCH residual model is dead code; raw Z wins

`fit_garch_residual` (`vol_models.py:37-83`) returns a conditional-σ
series, a GARCH-implied z, and an α+β persistence. It is **never called**
outside `tests/unit/test_vol_models.py` (`test_vol_models.py:12, 29, 37`).
A ripgrep for `from vol_models` / `fit_garch_residual(` returns only the
test file.

The sibling EWMA `Z_Vol` / `Spread_EwmaStd` (`quantitative_models.py:60-65`)
is also unused on the signal path:

- `backtest_zscore_meanreversion` reads `Z_Score` only
  (`quantitative_models.py:289, 292, 302`).
- `thesis_context.build_context` reads `Z_Score` only
  (`thesis_context.py:106-111`).
- `app.py` uses `Z_Score` for the hero strip, the alert threshold, the
  chart, and the CSV (`app.py:559, 1174, 1315, 1357, 1362`).
- The `regime_breakdown` vol-regime check uses a **third** definition —
  price-change std on the raw spread (`quantitative_models.py:539`).

The module docstring's claim that `Z_Vol` is "the real sigma" that
"reacts to regime change faster" (`quantitative_models.py:34-35`) is
aspirational. In the running code the raw 90d rolling Z wins every time.
Three vol estimators live in the repo and the weakest one is in
production. Fix: wire `Z_Vol` into the backtest and thesis, or delete
`vol_models.py`. Carrying dead quant code is worse than not having it.

### S1 (Blocker) — Engle-Granger only, no Johansen; hedge-ratio direction is frozen

`engle_granger` (`cointegration.py:100-176`) regresses
`Brent = α + β·WTI + ε` (`cointegration.py:132-138`) and runs ADF on the
residual. Two well-known E-G problems surface:

1. **Direction-dependence.** Regressing `WTI ~ Brent` gives a different β
   and can give a different ADF p-value. The "Dynamic hedge ratio" shown
   at `app.py:1223-1231` is one-sided by construction, not a Johansen
   eigenvector. For a pair as symmetric as Brent/WTI this matters in
   2022 and Q3 2025 when the "correct" dependent variable flipped.
2. **Single cointegrating vector, finite-sample power.** Johansen's trace
   and max-eigen tests are more powerful near structural breaks — the
   regimes `cointegration.py:3-6` explicitly calls out.

`statsmodels.tsa.vector_ar.vecm` and `coint_johansen` are never imported
(grep for `johansen|vecm` returns zero hits). Fix: add a Johansen test
cached on the same fingerprint and display both p-values — disagreement
is itself an informative regime signal.

### S1 (Blocker) — Half-life is computed and displayed but **not enforced**

`_half_life_from_residual` (`cointegration.py:73-97`) estimates the OU
half-life via AR(1) and it flows into `ThesisContext`
(`thesis_context.py:239-241`, `trade_thesis.py:99`) and the UI
(`app.py:1213-1222`). But:

- The `half_life_ack` checklist prompt at `trade_thesis.py:316-318` is the
  **literal string** `"I understand the implied half-life is ~N days."` —
  the `N` is never substituted. `coint_half_life_days` has no consumer
  outside the dataclass and one test assertion
  (`test_coverage_gaps.py:303`).
- `_apply_guardrails` (`trade_thesis.py:389-469`) clamps conviction on
  `coint_verdict == "not_cointegrated"` (line 449) but **does not clamp
  `time_horizon_days` against `coint_half_life_days`**. Nothing prevents
  a 60-day horizon on a 6-day-half-life residual, or vice versa.

The product reports mean-reversion speed and never lets it constrain
position duration — which is the one thing half-life actually tells you.
Fix: clamp `time_horizon_days` to `k · coint_half_life_days` (k≈3) and
template the number into the checklist.

### S2 — No VECM: the product models a flat spread, not an error-correction process

The whole trading stack operates on `Spread = Brent - WTI`
(`quantitative_models.py:50`), assuming a **unit** hedge ratio. The
cointegration module *does* estimate a β (`cointegration.py:137, 168`) —
and then discards it. The Z-score and backtest run on the flat spread.

Econometrically: a VECM on `(Brent_t, WTI_t)` gives (i) speed-of-adjustment
coefficients `α_B, α_W` describing *which* leg corrects, and (ii) a
β-weighted stationary residual. A flat spread with β≠1 contains a
deterministic drift that leaks into the "Z-score" and biases the backtest,
especially across 2015 (US export-ban) and 2022 (Urals). The only
acknowledgement in code is a caveat string fired when E-G p>0.10
(`trade_thesis.py:460-464`) — strictly on verdict, not on `|β-1|`. A β of
1.25 with p=0.04 triggers no guardrail. Minimum fix: switch the signal
residual from `Brent - WTI` to `Brent - β·WTI - α` using the same β
returned by `engle_granger`.

### S2 — Unit-root pre-test is missing; no KPSS complement

`adfuller` is invoked exactly once (`cointegration.py:139`), on the OLS
residual, with `autolag="AIC"`. Nothing confirms the **input series**
`Brent` and `WTI` are I(1) — a prerequisite of E-G. If either leg is
I(0) in a rolling window, the test is malformed and the ADF p-value is
not interpretable.

No KPSS complement exists — ADF and KPSS have opposite nulls and are
standard to cross-check for anything advertised in a UI. BIC would be
more conservative than AIC at n≈120 (the rolling window,
`cointegration.py:183`). The rolling E-G at `cointegration.py:179-216`
inherits AIC without re-evaluation and never asserts window-level
stationarity, so rolling "cointegrated" verdicts near breaks are noisier
than the tile implies.

### S2 — EWMA λ=0.94 is hard-coded and mis-aligned to the residual's mean

EWMA variance is computed on `Spread - Spread_Mean`
(`quantitative_models.py:60-61`) with `alpha = 1 - 0.94`. λ=0.94 is the
RiskMetrics **daily-equity-returns** convention — the docstring admits
as much (`quantitative_models.py:58-60`). For a residual of a rolling
mean on a daily oil spread, the optimal decay is empirical, not
inherited. No fit or validation is performed. `min_periods=10` on the
EWM is also much tighter than the 90-day rolling window, so `Z_Vol` is
defined long before `Z_Score` is — cross-row comparisons are misleading
during warm-up. Moot today because `Z_Vol` is unused (S1), but it will
bite the day someone flips the signal source.

### S2 — Backtest annualisation uses calendar days and mean hold

`backtest_zscore_meanreversion` computes Sharpe via
`sqrt(365 / mean_hold_days)` (`quantitative_models.py:351-355`). Two
errors: (i) **365 vs 252** — trade entries are trading-day-only, so
calendar-day annualisation biases Sharpe up by √(365/252) ≈ 1.20; (ii)
using *mean hold* as inter-trade time over-states under overlap.
Sortino (`quantitative_models.py:362-364`) and the rolling 12m Sharpe
(`quantitative_models.py:381-390`) inherit the same bias. Use 252
consistently with `thesis_context._realized_vol_pct`
(`thesis_context.py:50`).

### S3 — No Granger causality, no impulse-response on inventories

The product ingests EIA weekly inventory (`thesis_context.py:121-136`)
and uses it as a materiality input (`trade_thesis.py:759, 795-798`). No
causal model connects inventory shocks to price shocks: grep for
`grangercausal|irf|impulse` returns zero. Inventory affects the thesis
*only* via (a) a forced-flat guardrail when source is unavailable
(`trade_thesis.py:393-398`) and (b) slope-sign in the materiality
fingerprint. For a product whose hero countdown is "next EIA release"
(`app.py:571-579`), a small structural VAR on
`(ΔStocks, ΔBrent, ΔWTI)` with two lags would give an empirical
"expected reaction to a 5-Mbbl surprise." Today the thesis only says it
in English (`trade_thesis.py:528-529`).

### S3 — No regime-switching component; "regime" is used in three disjoint senses

The word "regime" appears 20+ times. (a) vol-percentile buckets in the
materiality fingerprint (`trade_thesis.py:765-771`), (b) median-split on
rolling vol in the blotter (`quantitative_models.py:525-562`), (c) the
high-vol sizing clamp in guardrails (`trade_thesis.py:427-446`). None
is a statistical regime model. `markov|hamilton|regime.switch` returns
zero hits. Given the product explicitly calls out structural breaks
(`cointegration.py:4-6`), a 2-state MSAR on the Z is the canonical tool
and its omission is a gap between stated model and claimed behaviour.

### S3 — Rolling E-G silently truncates the tail

`rolling_engle_granger` (`cointegration.py:179-216`) advances by
`step=20` with loop condition `while i <= len(idx)` at line 202. The
final window-end is the last `step`-aligned index, not the most recent
observation. On a 1,260-row frame with `window=120, step=20`, up to 19
days of the most recent history can be dropped unless
`(1260-120) % 20 == 0`. For a tile whose purpose is "is the pair
cointegrated *right now*", silently dropping the tail is a subtle bug.
Fix: after the loop, if `window_end < idx[-1]`, run one more window
ending at `idx[-1]`.

### S4 — Thresholds are magic numbers; no smooth conviction scaling

`engle_granger` hard-codes p=0.05 / p=0.10 as verdict boundaries
(`cointegration.py:158-163, 174-175`). The guardrail at
`trade_thesis.py:449` only fires on literal `"not_cointegrated"`, so a
pair with p=0.089 ("weak") triggers **no** conviction clamp. No
Bonferroni adjustment when rolling E-G runs ~60 tests on 5y. Replace
the three discrete buckets with a smooth `1-p` multiplier.

### S4 — Half-life AR(1) fit has no CI; 0.1-day precision is misleading

`_half_life_from_residual` (`cointegration.py:86-95`) fits OLS AR(1) and
inverts ρ deterministically. For ρ near 1 the estimator is severely
biased downward in finite samples (Kendall / Marriott-Pope). No standard
error, no CI. The UI displays `"{hl:.1f} days"` (`app.py:1216`) as if it
were worth 0.1-day precision. Cheapest win: round to whole days. Proper
fix: switch to `statsmodels.tsa.ar_model.AutoReg` and show a CI.
