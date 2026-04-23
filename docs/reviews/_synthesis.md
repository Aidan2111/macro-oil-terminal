# Phase B Synthesis — Macro Oil Terminal

> Aggregates the ten Phase A persona reviews under `docs/reviews/01..10`.
> Four sections: TL;DR → Top-20 action list → Scorecard → Phase C
> implementation order → Open questions for Aidan. Every row traces
> back to a numbered finding in a named review.

## TL;DR

The product has **adult scaffolding** — dataclass contracts, a five-clamp
guardrail, EIA/CFTC/crack/AIS plumbing, an audit JSONL, a rule-based
fallback — and the individual quant helpers (EWMA, GARCH, Engle-Granger,
Monte-Carlo, VaR/ES) are written with real care. What the terminal needs
most urgently is to **stop lying to itself about the backtest**: the
same-bar look-ahead in the Z, the zero-cost fill model, and the rolling
stats that leak into `bt_hit_rate`/`bt_sharpe` feeding the LLM prior. The
top three fixes are (1) shift rolling mean/std by one bar and feed
walk-forward last-fold hit-rate into the prior, (2) set realistic
slippage/commission defaults and thread hedge ratio into the backtest,
(3) render the `plain_english_headline` + `invalidation_risks` that the
backend already generates — it is currently dead code between the schema
and the user's screen.

---

## 1. Top-20 Ranked Action List — Impact × (1/Effort)

| # | Severity | Effort | Source persona(s) | File:line | Finding | Proposed fix |
|---|---|---|---|---|---|---|
| 1 | CRITICAL | S | 01 (Stats), 04 (ML F3) | `quantitative_models.py:50-55, 301-310` | Rolling mean/std include bar `t` itself; signal and fill share a timestamp. Contaminates every downstream metric (Sharpe, Sortino, Calmar, rolling-12m, walk-forward, Monte-Carlo). | Add `.shift(1)` to the rolling mean and std; verify backtest iterates on prior-bar Z. Regression test: a series that would yield Z=0 under leakage must yield non-zero Z under the fix. Mirror in the EWMA path. |
| 2 | CRITICAL | XS | 09 (UX S1) | `trade_thesis.py:272,924-949`, `app.py:768-787` | `plain_english_headline` is generated, schema-required, and never rendered. Hero leads with uppercase imperative pill, no calibrated hedging layer. | Render `thesis.plain_english_headline` as first child of `_render_hero_band` with `data-testid="plain-english-headline"`. |
| 3 | CRITICAL | S | 02 (S1-2), 05 (S2 liquidity), 04 (F11) | `quantitative_models.py:248-253,315-317` | Backtest defaults are zero slippage and zero commission; `bt_sharpe` / `bt_hit_rate` feeding the LLM are gross-of-cost. | Default `slippage_per_bbl=0.02`, `commission_per_trade=2.50`; expose a "costs" toggle (never allow true zero in UI); sample slippage LogNormal for MC stress. |
| 4 | CRITICAL | S | 04 (F2) | `trade_thesis.py:405-414`, `quantitative_models.py:246-418` | `bt_hit_rate` is 100% in-sample and feeds the LLM conviction prior; look-ahead contaminates every calibration clamp. | Feed walk-forward last-fold hit-rate into `ThesisContext.bt_hit_rate`, or compute on data older than `now - k*avg_hold_days`. |
| 5 | CRITICAL | S | 09 (UX S3) | `trade_thesis.py:172,186,411-464`, `app.py` (no read) | `invalidation_risks` and `data_caveats` are schema-required, guardrail-appended, and never rendered — classic confirmation bias by omission. | Render `invalidation_risks[:3]` as caption inside `_render_hero_band`; surface `data_caveats` as a dedicated warning strip when non-empty. |
| 6 | CRITICAL | S | 08 (F1), 07 (F6) | `providers/pricing.py:44,56,68,88`, `_yfinance.py:21`, `_polygon.py:44` | `fetched_at = pd.Timestamp.utcnow()` is naive; `datetime.utcnow()` is deprecated. Test fixtures use live wall-clock; EIA countdown breaks 8 months/yr. | Replace with `pd.Timestamp.now(tz="UTC")` across providers; adopt `zoneinfo.ZoneInfo("America/New_York")` for EIA/EIA-release math; add `freezegun` for tests. |
| 7 | HIGH | S | 02 (S2 hedge), 03 (VECM) | `quantitative_models.py:314`, `trade_thesis.py:356-380` | Backtest treats Brent-WTI as 1:1 bbl and ignores the E-G `hedge_ratio` that is already computed and surfaced to `ThesisContext.coint_hedge_ratio`. | Thread `coint_hedge_ratio` through `backtest_zscore_meanreversion`; use `β`-adjusted residual as the signal and in Tier-3 futures sizing ("long 7 CL / short 10 BZ"). |
| 8 | CRITICAL | L | 02 (S1-1) | `providers/_yfinance.py:25-27,65-66`, `quantitative_models.py:50` | Continuous front-month `BZ=F - CL=F` with no roll adjustment — ~24 fake roll-day gaps per year leak into the signal, the backtest, and the EWMA sigma. | Panama-adjust history (back-adjust legacy by roll delta) OR drop roll-day±1 bars. Design call required — see Open Question #1. |
| 9 | HIGH | S | 05 (S2 drawdown), 01, 04 | `quantitative_models.py:342-345`, `trade_thesis.py:389-469` | `max_dd` is in-sample and never feeds a guardrail; no time-under-water; no consecutive-loss circuit-breaker. | Propagate `max_dd_days`; clamp size when `size × max_dd > 5% capital`; clamp to flat when rolling-20-trade hit rate < 40%. |
| 10 | HIGH | M | 01 (#3), 02 (S3), 03 (#S2), 04 (F7), 05 (S3), 06 | `quantitative_models.py:347-355` | Sharpe is per-trade dollar PnL with `ddof=0` and `sqrt(365/mean_hold_days)` annualisation — biased up, mixes calendar/trading days, not returns-based. | Compute Sharpe on daily equity-curve returns with `ddof=1` and `sqrt(252)`. Rename per-trade metric to `mean_trade_pnl_t_stat`. Return `NaN` when `n_trades < 20`. |
| 11 | HIGH | XS | 03 (S1 half-life), 05 (S3 placeholder) | `trade_thesis.py:316-318`, `:449-469` | Half-life checklist is the literal string `"~N days"`; `coint_half_life_days` exists but no consumer substitutes it; nothing clamps `time_horizon_days` against half-life. | Format with `f"...~{ctx.coint_half_life_days:.0f} days."`; clamp `time_horizon_days` to `k × coint_half_life_days` (k≈3) in `_apply_guardrails`. |
| 12 | HIGH | M | 01 (#2), 05 (S2 bands), 09 (S12) | `language.py:200-221` | Stretch bands `<0.7 / <1.3 / <2.3 / <3.2` assume a standard-normal Z that the rolling-std-of-coint-residual does not deliver; empirical 99th pct of |Z| ≈ 2.7-2.9. | Replace hard-coded cutoffs with empirical quantiles (50/80/95/99 of trailing-5y `|Z|`), recalibrated daily; or freeze and rename to "Low/Mid/High band." Make regime-conditional on `vol_spread_1y_percentile`. |
| 13 | HIGH | XS | 02 (S2 copy), 09 (S2, S6, S8) | `language.py:60-64,61-64,78-83`, `theme.py:410-438` | Stance copy "Buy / Sell / Wait" is prescriptive not hypothetical; green/red glow visually rewards action; WAIT is grey and "boring"; "Stretched" vs "dislocation" framing clashes. | Rename to "Lean long / Lean short / Stand aside"; use amber `--warn` for WAIT; standardise prose on "stretch" per the UI label; desaturate directional pills. |
| 14 | HIGH | S | 03 (S1 Garch), 01 (#8), 03 (EWMA) | `vol_models.py:37-83`, `quantitative_models.py:60-65` | GARCH residual model and EWMA `Z_Vol` are dead code — backtest, thesis, hero, alerts all read raw `Z_Score`. Three vol estimators in repo; the weakest is in production. | Wire `Z_Vol` into the backtest and thesis signal path, OR delete `vol_models.py`. Carrying unused quant code is worse than not having it. |
| 15 | HIGH | S | 06 (#1, #2) | `providers/_eia.py:37-40`, `thesis_context.py:122-132` | Physical structural layer missing: no Midland-Houston diff, no WTI-Houston export netback, no gasoline/distillate product inventory, no freight. LLM sees spread but cannot see barrel. | Add `WGTSTUS1` + `WDISTUS1` to `_SERIES_MAP`; add `PET.WCREXUS2.W` (weekly US crude exports) as an arb-openness proxy. Two new `ThesisContext` fields. |
| 16 | HIGH | M | 07 (F1), 07 (F2) | `tests/unit/test_*.py`, `requirements.txt` | No property-based tests (`hypothesis` absent); no historical-event regressions (2020-04 negative WTI, 2022-02 Ukraine, 2015 export-ban); `test_runner.py` is the prod gate, not pytest. | Add `hypothesis>=6.100`; write `tests/unit/test_properties_quant.py`; check in gzipped historical fixtures; promote pytest to `cd.yml` gate with `--cov-fail-under=85`. |
| 17 | HIGH | M | 05 (S1 stress), 06 (#7) | `quantitative_models.py` (no stress fn), `thesis_context.py:201-257` | No stress-test replay of historical regime shocks; `gross_per_bbl` has no bound, no margin, no forced liquidation; no choke-point transit proxy. | Add `stress_scenarios` list to `ThesisContext`: 2020-04 neg-WTI, 2022 Ukraine, 2014 OPEC; plus synthetic "+5σ in 1 bar"; block entry when stress-PnL > 5% capital. |
| 18 | HIGH | S | 02 (S2 EIA DST), 08 (F3, F4) | `thesis_context.py:67-84,194-199` | `_hours_to_next_eia_release` hard-codes 14:30 UTC, ignoring DST and federal holidays; NYMEX session model misses Sunday re-open + Good Friday/Thanksgiving. | Compose with `pandas_market_calendars("CMES")` + `zoneinfo.ZoneInfo("America/New_York")`; add deferred-release table for EIA holidays. |
| 19 | HIGH | S | 08 (F5) | `trade_thesis.py:335`, `providers/_yfinance.py:25` | USO/BNO ETF leg is advertised in hero + backtest UI but **no provider fetches** it; if added, `auto_adjust=False` misses USO's 2020 reverse splits. | Either delete the Tier-2 ETF leg until a provider exists, OR add `_yfinance.fetch_etf(["USO","BNO"])` with `auto_adjust=True`. Design call — see Open Question #3. |
| 20 | HIGH | S | 10 (S1-a), 10 (S1-c) | `app.py:1519-1616,369-426` | Walk-forward + Monte-Carlo + regime-breakdown run uncached inside an expander; every slider tweak pays O(200×N_bars) Python loop. Fingerprint `f"{len(df)}-{df.index[-1]}"` collides on backfills — stale trades blotter after yfinance retry. | Wrap WF/MC/regime in `@st.cache_data` keyed on `(_fp(spread_df), entry_z, exit_z, slippage, commission)`; switch `_fp` to a content hash (`md5(pd.util.hash_pandas_object)`). |
| 21 | HIGH | M | 08 (F7) | `trade_thesis.py:725-743`, `app.py:721-740` | Audit JSONL appends are not atomic (multi-worker tears > 4096 B), not deduped on `context_fingerprint`, not rotated; `except Exception: pass` swallows errors. | Wrap writes in `fcntl.flock(LOCK_EX)` or migrate to SQLite WAL; add fingerprint dedupe; log exceptions. |
| 22 | HIGH | M | 05 (S2 Kelly), 04 (F11) | `trade_thesis.py:164,416-446` | Schema accepts `method = "kelly" / "volatility_scaled"` but nothing computes Kelly or vol-target sizing. Post-cost expected edge never checked against conviction. | Compute `bt_kelly_fraction` and `bt_half_kelly_fraction` from `bt_hit_rate` + avg win/loss; clamp `suggested_pct_of_capital ≤ half_kelly × 100` when method = "kelly"; clamp conviction ≤ 3 when post-cost edge < 0. |
| 23 | MEDIUM | S | 10 (S2-c) | `app.py:1122-1128` | Hero thesis LLM call fires synchronously inside the render pass; Azure OpenAI latency (2-10s) ladders into first-paint on every first session. | Render placeholder hero (the `thesis is None` branch already exists), kick LLM to background thread, `st.rerun()` on completion. |
| 24 | MEDIUM | S | 03 (#S2), 03 (ADF/KPSS) | `cointegration.py:132-139` | E-G regresses `Brent ~ WTI` only (direction-frozen); no Johansen; no ADF on the raw spread; no KPSS cross-check. Pair can cointegrate with β=1.15 and have a non-stationary β=1 spread. | Add ADF on raw spread; add KPSS complement; add Johansen trace + max-eigen; switch signal residual to `Brent - β·WTI - α`. Design call — see Open Question #2. |
| 25 | MEDIUM | M | 01 (#5,#7), 04 (F8) | `quantitative_models.py:424-519` | No multiple-testing correction on walk-forward grid; no bootstrap CI on PnL / Sharpe / max-DD; MC perturbs `entry_z` but has no null-hypothesis shuffled-Z baseline. | Add permutation baseline (shuffle Z 1000×); Benjamini-Hochberg on walk-forward grid when >3 windows; block-bootstrap CIs for backtest headline metrics. |
| 26 | MEDIUM | S | 04 (F5, F6, F9) | `trade_thesis.py:571-719, 648`, `thesis_context.py:87-257` | LLM conviction is never calibrated against realised hit rate; no drift monitoring on input features (PSI/KS); Azure OpenAI call has no `seed` so fingerprint→thesis isn't deterministic. | Nightly ECE/Brier job from `data/trade_theses.jsonl`; PSI tile on 5-6 load-bearing features; pin `seed=hash(ctx.fingerprint()) & 0xFFFFFFFF` in the API call. |
| 27 | MEDIUM | XS | 05 (S3 inf), 01 (#10) | `quantitative_models.py:360-364,372` | `Sortino` / `Calmar` return `float("inf")` when denominators are zero, poisoning the audit JSONL and breaking downstream histograms. | Return `NaN` + companion `metric_defined: bool`; update tests. |
| 28 | MEDIUM | L | 08 (F5 ETF split), 08 (F6 cache), 08 (F8 ffill) | `providers/_yfinance.py:48`, `_eia.py:229-231`, `_cftc.py:170-203` | `.bfill()` paints historical NaN with future values; EIA/yfinance ffill hides gaps; CFTC cache TTL straddles Friday 15:30 ET release. | Drop `bfill()`; keep raw frames + `missing_mask`; key CFTC cache on `utcnow().date().isoformat()` modulo Friday release; persist to `data/.cache/*.parquet`. |
| 29 | MEDIUM | XS | 02 (S3 COT), 06 (#10) | `providers/_cftc.py`, `quantitative_models.py:246` | CFTC positioning is fetched but not folded into backtest entry filter; `commercial_combined_net = producer + swap` never computed. | Expose `entries_require_coint: bool` + `cftc_mm_zscore_filter`; compute `commercial_combined_net` in `thesis_context.py`. |
| 30 | LOW | XS | 01 (#9), 02 (S3 depletion), 04 (F1) | `quantitative_models.py:73-158` | `forecast_depletion` fits 4 weekly points, reports in-sample R², extrapolates 3 years. Textbook extrapolation failure. | Default `lookback_weeks=12`; cap projection horizon at `3×lookback_weeks`; replace R² with LOO-MAE + slope SE; render date band `[date_lo, date_hi]`. |

**Note:** rows 16, 25, 26, 28 each pack 2-3 tightly-coupled sub-findings
so the table stays readable; each sub-fix is small but they share a
file neighbourhood. Rows 8, 19, 24 are flagged as design-decision-
dependent (see Open Questions below).

---

## 2. Scorecard — Before Phase C

Scoring rules: 3+ CRITICALs → max 4; 2+ HIGHs → max 6; only MEDIUM/LOW →
7-8; no serious findings → 9-10.

| Dimension | Score (1-10) | Top weaknesses | Top strengths |
|---|---|---|---|
| Statistical rigor | **3** | Same-bar look-ahead in rolling Z; Gaussian-band mislabel; Sharpe on per-trade dollars with `ddof=0`; no multiple-testing correction; no CIs on headline metrics | `std.replace(0, np.nan)` + inf-scrub is clean; cointegration has short-series guard; seeded synthetic tests recover α+β from GARCH DGP |
| Quant-trader realism | **3** | Zero-slippage / zero-commission defaults; no roll adjustment on continuous front-month; 1:1 hedge ratio ignores E-G β; daily signal → intraday execution fiction | EWMA Z sidecar, audit JSONL, five-clamp guardrail, crack wiring scaled gal→bbl correctly |
| Econometric correctness | **4** | GARCH + EWMA are dead code (raw Z wins); E-G only (no Johansen); half-life computed but never enforced; no VECM (flat spread assumes β=1); no ADF/KPSS on raw spread | Short-series guard and `0 < ρ < 1` half-life guard are correct; synthetic cointegration tests use shared-trend construction |
| ML hygiene | **4** | In-sample `bt_hit_rate` feeds LLM prior; 4-point fit extrapolated 3 yrs; no conviction calibration (no ECE/Brier); no PSI/KS drift monitor; LLM `seed` unpinned | Monte-Carlo takes a seed; rule-based fallback exists; walk-forward is the right instinct |
| Risk management | **4** | Historical-only VaR on thin sample, ES-95 (not 97.5); no stress replay of 2020-04/2022/2015; no leverage/margin/ruin check; Kelly named, never computed; max-DD never de-risks | Five-clamp `_apply_guardrails`; VaR/ES present at all; vol-regime sizing clamp; `test_backtest_risk_metrics_present` in CI |
| Energy-markets coverage | **4** | No Midland-Houston diff; no gasoline/distillate inventory; no freight (VLCC/Suezmax TCE); no OPEC+ compliance; sanctioned tonnage fetched but not wired to `fleet_delta`; Cushing utilisation % absent | Cushing 4w slope present; 3-2-1 crack correctly scaled; CFTC MM-Z is a real signal; AIS pipeline collects real data |
| Testing rigor | **6** | No property-based tests on quant math; no historical-event regressions; `test_runner.py` is the prod gate, not pytest; `wait_for_timeout(500)` flake; no snapshot/visual-regression; `eia_fixture` falls through to real network | ~47 files, 75% line coverage on happy paths; seeded synthetic generators; inf/NaN hardening in `_clamp`; malformed→valid-retry test for LLM parse |
| Data engineering | **4** | Naive `fetched_at` tz everywhere; no stale-data detection; EIA DST wrong 8 months/yr; NYMEX session model ignores holidays + DST; USO/BNO advertised but never ingested; audit writes race on multi-worker | Clean `fetch_* → Result` contract; no silent synthetic fallback; per-provider source URLs; `InventoryResult` dataclass discipline |
| Behavioural UX / debiasing | **3** | `plain_english_headline` is dead code; `invalidation_risks` + `data_caveats` never rendered; stance pill is prescriptive uppercase + glow; disclaimer is `text-muted` at 10:1 visual ratio to stance; "Very High" 10/10 ceiling framing | Schema has all the right fields (invalidations, caveats, headline, key drivers); guardrails append to `data_caveats`; `describe_stretch` is behaviourally sound language |
| Performance | **6** | WF/MC/regime uncached inside expander; `_fp()` collision on yfinance backfill; LLM in render pass ladders Azure latency into first paint; ticker fragment has no backpressure; aisstream 20s block on main thread | `@st.cache_data` on simple backtest; `Scattergl` for 5y bars; CSS once-per-session guard; keep-warm workflow exists; T10 polished-cold is 1.6s local |

**Weighted summary:** the product is strong on *scaffolding* and
*audit discipline* (clean contracts, guardrails, fallback, seeded
tests, no synthetic-data lies) and weak on *truthfulness of headline
numbers* (look-ahead, cost model, in-sample calibration) and on
*presentation of uncertainty* (UI hides the hedging layer the schema
built for it).

---

## 3. Phase C Implementation Order

Sequenced so high-leverage fixes unblock downstream metrics, and
independent workstreams can parallelise on separate branches.

1. **Row 1 — shift rolling Z by one bar.** Unblocks every backtest metric
   (#4, #9, #10, #14, #25). Do this first, on its own branch, with a
   regression test. Everything else downstream recomputes once.
2. **Row 3 + Row 10 (parallel branch) — realistic slippage/commission
   defaults + Sharpe on daily returns.** These two together restore
   integrity of `bt_sharpe` / `bt_hit_rate` before they touch the LLM.
3. **Row 4 — feed walk-forward last-fold hit-rate into
   `ThesisContext.bt_hit_rate`.** Requires Rows 1 and 3 to be correct
   first, otherwise you're calibrating on a still-contaminated curve.
4. **Row 2 + Row 5 + Row 13 (UX branch).** Render
   `plain_english_headline`, `invalidation_risks`, `data_caveats`; rename
   stance copy; fix disclaimer salience. Independent of the quant
   branch — ship in parallel. This is the single cheapest visible win.
5. **Row 11 — template half-life into checklist + clamp `time_horizon_days`.**
   XS effort, closes a material behavioural gap. Ship next.
6. **Row 6 — tz-aware timestamps + `freezegun` for tests.** Needed before
   Row 18 (holiday calendar) so the test harness is deterministic.
7. **Row 7 — thread `coint_hedge_ratio` through the backtest and Tier-3
   sizing.** Requires Row 1 first (shifted residual).
8. **Row 18 — `pandas_market_calendars` + `zoneinfo` for EIA + NYMEX
   session + EIA holidays.** Unblocks the `catalyst_clear` guardrail.
9. **Row 16 — property-based tests + historical-event regressions +
   promote pytest to prod gate.** Parallelisable with the quant work;
   first hypothesis run is expected to surface 2-3 real bugs per
   persona 07's note.
10. **Row 20 — cache WF/MC/regime + content-hash fingerprint.**
    Independent perf branch; a one-sitting fix with large warm-TTI win.
11. **Row 23 — move LLM call off the render thread.** Same perf branch
    or its own; noticeable first-paint win for first-session users.
12. **Row 9 — max-DD / consecutive-loss circuit-breakers; Row 22 — Kelly +
    vol-target + post-cost edge clamp.** Both require Rows 1, 3, 10 to be
    correct; bundle into a "risk discipline" branch.
13. **Row 17 — stress-scenario replay.** Builds on corrected backtest
    (Row 1) and on realistic costs (Row 3); needs a one-time fixture
    commit of historical shocks.
14. **Row 12 — replace Gaussian stretch bands with empirical quantiles +
    regime-conditioning.** Deferred until after Row 1 because the
    quantiles should be computed on the corrected Z.
15. **Row 14 — wire `Z_Vol` into signal path OR delete `vol_models.py`.**
    Design call with Aidan — see Open Question #4.
16. **Row 15 — add `WGTSTUS1`, `WDISTUS1`, `PET.WCREXUS2.W` to EIA
    provider.** Independent data branch; three-line change with high
    information gain.
17. **Row 21 — atomic audit writes + dedupe + rotation.** Independent
    data-engineering branch; ship with Row 26 (calibration nightly job)
    since both touch the audit pipeline.
18. **Row 26 — nightly ECE/Brier + PSI drift tile + pin LLM `seed`.**
    Builds on Row 21.
19. **Row 27 — fix `inf` Sortino/Calmar → `NaN + metric_defined`.**
    Trivial, bundle with Row 10.
20. **Row 28 — drop `bfill`, expose `missing_mask`, persist CFTC cache.**
    Independent data branch.
21. **Row 29 — CFTC filter into backtest + `commercial_combined_net`.**
    Parallelisable with Row 15.
22. **Row 30 — `forecast_depletion` defaults + horizon cap + LOO-MAE.**
    Trivial, bundle with Row 15.
23. **Row 24 — Johansen + KPSS + β-adjusted residual.** Design call —
    see Open Question #2.
24. **Row 8 — continuous-front-month roll adjustment.** Design call —
    see Open Question #1. Large scope; punt until after the quick wins.
25. **Row 19 — USO/BNO decision.** Design call — see Open Question #3.

Rows 8, 19, 24 are deliberately last because they need Aidan's call on
scope / direction. Everything before them is a fix we know how to
execute.

---

## 4. Open Questions for Aidan

1. **Roll adjustment (Row 8).** Should we (a) panama-adjust the
   continuous front-month history, (b) drop roll-day±1 bars, or (c)
   actually hold M+2 and roll explicitly so PnL includes the real roll
   cost? Persona 02 votes (a)+(c). **My recommendation: (a) for signal +
   (c) for backtest** — adjusting history fixes the ~24 fake gaps/yr
   that leak into the Z, and the explicit-roll backtest is the only
   honest PnL for the trader-facing number. Estimated 2-3 days of work.

2. **Econometric depth (Row 24).** Ship Johansen **alongside**
   Engle-Granger and display both p-values, or **replace** E-G with
   Johansen? Persona 03 argues disagreement between the two is itself a
   regime signal. **My recommendation: ship both, cache on the same
   fingerprint, surface disagreement as a caveat string.** Replacing
   E-G breaks existing tests and removes the hedge-ratio we now rely
   on in Row 7.

3. **USO/BNO ETF leg (Row 19).** Ship a real ETF provider with
   `auto_adjust=True` and support the Tier-2 retail user, or **delete
   the leg entirely** until a desk has time? Persona 08 flags the 2020
   reverse splits as a compliance-adjacent risk. **My recommendation:
   delete now, ship later.** A visibly missing leg is less harmful than
   a silently split-contaminated one.

4. **GARCH / EWMA `Z_Vol` (Row 14).** Wire `Z_Vol` into the backtest +
   thesis signal path (closes Persona 03's "three vol estimators, the
   weakest is in production"), or **delete `vol_models.py` entirely**?
   **My recommendation: wire it in behind a feature flag**, run both
   paths in the walk-forward for a cycle, then pick the winner with
   actual hit-rate evidence. Deleting the module ships dead code's
   grave, but wiring it without a shadow comparison ships a Sharpe
   change with no justification.

5. **UI stance-copy rename (Row 13).** Do we rename "Buy the spread /
   Sell the spread" to "Lean long / Lean short" (persona 09's S2), or
   keep the imperative copy and soften only the glow + colour? A rename
   touches every test that greps stance strings. **My recommendation:
   rename copy + amber WAIT + disclaimer-in-hero in one atomic UX
   branch**, update snapshots, and own the test churn once.

---

*Generated Phase B, 2026-04-22.*
