# Q3 prediction-quality slice — Engle-Granger + regime + GARCH + tail-risk

Replaces the "vibes" stretch reading with quant rigor on every thesis card,
and lifts the backtest tile from a 2-metric summary (Sharpe, Max DD) to a
desk-grade 6-metric panel.

## Visible end-state on the live SWA

| Surface | Before | After |
| --- | --- | --- |
| Hero card — coint pill | (absent) | `Coint p=0.034 (HL 4.2d)` with plain-English tooltip |
| Hero card — regime badges | (absent) | `[Contango] [High vol]` two-pill row, hover-explainable |
| Hero card — stretch | rolling-std Z only | rolling Z by default, `Advanced` toggle swaps to GARCH-normalised σ |
| Backtest tile — risk row | Sharpe + Max DD | + Sortino + Calmar + VaR-95 + ES-97.5 (4-up tooltipped strip) |

All four surfaces ship with hover-tooltips that explain the stat in
plain English — the hero card stops requiring a quant background to
read.

## Backend — `backend/services/`

| File | Public surface | Notes |
| --- | --- | --- |
| `cointegration_service.py` | `compute_cointegration_for_thesis(spread_df) -> CointegrationStats` | Wraps the existing `cointegration.engle_granger`. Content-hash cache (SHA-256 over Brent + WTI bytes) so the SSE poll path doesn't re-OLS on every hit. FIFO eviction at 16 entries. Never raises — pathological inputs return `verdict="inconclusive"` with a populated `message`. |
| `regime_service.py` | `detect_regime(df) -> RegimeStats` | Term structure: Brent − WTI sign with a $0.25 dead-zone for "flat". Vol bucket: bucketed 1y percentile of the 20-day annualised realized vol of the spread. <33 → low, 33–66 → normal, >66 → high. |
| `garch_stretch.py` | `compute_garch_normalized_stretch(spread_df) -> tuple[float, dict]` | Wraps `vol_models.fit_garch_residual` (which is itself defensive). Returns `(z, diagnostics)` where the diag dict carries `ok`, `sigma`, `persistence`, `fallback_used`, `fallback_reason`, `n_obs`. |

`thesis_service._build_thesis_context` now invokes all three services
and feeds their outputs into `thesis_context.build_context` via three
new optional kwargs (`coint_info`, `regime_info`, `garch_info`). Each
service has its own try/except in the builder so a single failure
collapses to a missing pill rather than a 500.

`ThesisContext` gains nine new fields, all `Optional[...] = None`:

```text
regime_term_structure   regime_vol_bucket   regime_vol_percentile   regime_realized_vol_20d_pct
garch_z   garch_ok   garch_sigma   garch_persistence   garch_fallback_reason
```

The cointegration fields (`coint_p_value`, `coint_verdict`,
`coint_hedge_ratio`, `coint_half_life_days`) already existed in
`ThesisContext`; this PR is the first one that actually populates them.

`trade_thesis.SYSTEM_PROMPT` is extended with explicit instructions
for the model to cite the four new prediction-quality fields rather
than ignore them. The schema additions are backwards-compatible
(every new field defaults to `None`), so legacy audit-log records
deserialise unchanged.

`quantitative_models.backtest_zscore_meanreversion` adds an `es_975`
key (Expected Shortfall at the 97.5% confidence level — average loss
across the worst 2.5% of trades). `backtest_service.run_backtest`
propagates it through to the HTTP payload.

## Frontend — `frontend/components/`

| File | Mounts on | Persists |
| --- | --- | --- |
| `hero/CointegrationStat.tsx` | hero card, below stance row | (stateless) |
| `hero/RegimeBadges.tsx` | hero card, alongside coint pill | (stateless) |
| `hero/AdvancedToggle.tsx` | hero card, right side of the same strip | sessionStorage |
| `charts/BacktestRiskMetrics.tsx` | extends `BacktestChart` stats row | (stateless) |

Wiring happens in `frontend/components/hero/TradeIdeaHeroClient.tsx`
(adds the new strip) and `frontend/components/charts/BacktestChart.tsx`
(adds `<BacktestRiskMetrics>` immediately under the existing
`<StatsRow>`). `frontend/types/api.ts` gains the new `context` shape
fields and the `es_975` field on `BacktestLiveResponse`.

### Storage choice — sessionStorage, not localStorage

The brief originally said localStorage, but the Cowork environment
disables localStorage. `AdvancedToggle.tsx` uses `window.sessionStorage`
instead, gated through a `useEffect` so SSR + first-paint don't
mismatch and a try/catch around every read/write so private-mode and
sandboxed iframes don't throw. Single-tab persistence is the desk
convention anyway.

### Page-weight regression — none

`arch` and `statsmodels` are imported only inside the lazy
`backend.services.*` modules. `node_modules` is not touched. The
GARCH fit lives entirely in the backend; the React surface only
reads the resulting numbers off the thesis context blob.

## Tests — `tests/unit/`

Four new files, 26 cases, all green under `.venv313` (Python 3.13.12,
numpy 2.4, pandas 3, sklearn 1.8, arch 8, statsmodels 0.14.6).

| File | Coverage |
| --- | --- |
| `test_cointegration_service.py` | happy path; hash-cache hits skip re-computation; short / empty / column-missing inputs collapse to `inconclusive` + populated `message`; `to_dict` scrubs NaN to None |
| `test_regime_service.py` | contango / backwardation / flat fixtures; high / low vol bucket fixtures (independent random walks for Brent/WTI); short / empty windows return `unknown`; `to_dict` NaN scrub |
| `test_garch_stretch.py` | well-behaved fixture → ok=True with finite z; short window → fallback with reason; missing module (monkey-patched ImportError) → fallback; missing column → fallback; empty frame → fallback; GARCH σ ≠ rolling std on a vol cluster (otherwise the toggle would be cosmetic) |
| `test_backtest_risk_metrics.py` | full metric set is present; ES-97.5 ≤ ES-95 (deeper tail = no less severe); Sortino ≥ Sharpe on a left-skewed fixture; Calmar finite + positive when DD pair exists; empty blotter → all-zero metrics; the HTTP shaper propagates `es_975` |

Existing test suite (264 unit tests across the touched modules) still
passes — no regressions in `test_cointegration.py`, `test_vol_models.py`,
`test_quantitative_models.py`, `test_thesis_context_full.py`, or
`test_thesis_service_context.py`.

`backend/tests/` failures (route-less `create_app()`) are pre-existing
on `origin/main` and tracked in `scripts/bump-deps-run.PR_BODY.md` —
NOT a Q3 regression.

## On windows too short to fit GARCH(1,1)

`vol_models.fit_garch_residual` requires `len(residual) >= 100` to
attempt a fit. The residual stream consumed by `garch_stretch` is
`Spread − Spread_Mean`; with the 90-day rolling mean, ~90 leading
observations are NaN before the residual stabilises. So:

| Pricing window | Usable residual | GARCH fit? |
| --- | --- | --- |
| < 190 trading days (~9 calendar months) | < 100 | **No** — rolling-std fallback, `fallback_reason="residual series too short (n=N, need 100)"` |
| 190 – 250 trading days | 100 – 160 | Marginal — ML solver occasionally diverges; `ok=false` with `note` from `arch.fit` |
| ≥ 250 trading days (1 trading year) | ≥ 160 | **Yes** — fits reliably |

The hero card never blanks: when `garch_ok=false`, the toggle is
disabled (greyed) and the rolling-std stretch keeps rendering. The
tooltip surfaces the fallback reason verbatim so the operator knows
*why* the upgrade isn't available.

The production yfinance pricing window pulls ≥ 1 year of daily bars
on every poll, so the production path is always in the "fits
reliably" tier. The marginal tier only kicks in for cold-start /
truncated-data debug fixtures.

## Caching notes

* Cointegration: content-hash cache (FIFO, 16 slots) inside
  `cointegration_service`. Identical (Brent, WTI) tapes hit in O(n)
  hash time and skip the OLS + ADF entirely.
* Regime: stateless — the math is cheap (one rolling stdev), no cache
  needed.
* GARCH: not cached at the service layer — the `_TTLCache` in
  `backend/main.py` already wraps the SSE thesis-build path at 30s, so
  GARCH only fits once per cache window.

## Out of scope (deferred)

* **Johansen trace** — `CointegrationStats.johansen_trace` is on the
  schema but always emits `None`. Wiring `statsmodels.tsa.vector_ar.vecm.coint_johansen`
  is a single-file follow-up; not blocking the Q3 ship.
* **Per-thesis cache invalidation on regen** — the SSE poll cycle
  hits the `_TTLCache` 30s window first, so this isn't yet a hot
  path. Worth a look if poll cadence drops below 10s.
* **Frontend regression tests for the new components** — the existing
  vitest suite covers `BacktestChart` and `TradeIdeaHero`; new tests
  for `CointegrationStat`, `RegimeBadges`, `AdvancedToggle`,
  `BacktestRiskMetrics` are a fast follow-up. Backend behaviour is
  fully tested under `tests/unit/test_*_service.py`.

## Operator note

Run `bash scripts/q3-prediction-quality-run.sh` from the host to ship.
The runner is idempotent — re-execution after a partial failure picks
up where it left off (branch reset to origin/main + same source
changes already on disk → same commit → same PR).
