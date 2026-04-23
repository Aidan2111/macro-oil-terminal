# Persona 07 — QA / Test-Rigor Engineer (Phase A)

Lens: coverage (line + branch), property-based testing, fuzz, historical-event
regressions, flakiness, determinism, mocks-vs-integration balance, test naming
and organisation, snapshot testing. Everything below cites file+line.

Findings are severity-ranked — **P0** (correctness risk, fix before next
release), **P1** (real gap, schedule this sprint), **P2** (polish).

---

## F1 — [P0] No property-based tests on the quant math, despite it being the product

`cointegration.engle_granger`, `quantitative_models.compute_spread_zscore`,
`quantitative_models.backtest_zscore_meanreversion`, `forecast_depletion`,
`monte_carlo_entry_noise` and `vol_models.fit_garch_residual` are all pure
numeric functions where invariants dominate. Today every test is a
hand-picked synthetic with a hard-coded seed:
`tests/unit/test_quantitative_models.py:12-18` (one seeded frame),
`tests/unit/test_cointegration.py:10-26` (one seed), `test_vol_models.py:11-26`
(one simulated GARCH path). `hypothesis` isn't in `requirements.txt`
(grep confirms — only referenced in `docs/quant_review_2026-04-22.md`).

What `hypothesis` would catch that we currently can't:

- **Monotonicity** of `compute_spread_zscore` under series scaling — multiplying
  both legs by a positive constant should leave Z-scores invariant. No test
  asserts this.
- `monte_carlo_entry_noise` currently only asserts `pnl_p05 <= pnl_p95`
  (`test_quantitative_models.py:80-81`) — a property test over random spread
  frames would catch percentile inversions, NaN leakage, and n_runs≤1 edge cases.
- `forecast_depletion` with lookback_weeks ∈ [1, 520], floor_bbls ∈ [0, 2e9] —
  the current tests are two synthetic shapes (`test_quantitative_models.py:27-45`).
- `engle_granger` hedge-ratio sign invariance under swapping y↔x.

Fix: add `hypothesis>=6.100` to `requirements.txt`, add a
`tests/unit/test_properties_quant.py` covering ~6 strategies. Expect 2-3 real
bugs to fall out of the first run.

## F2 — [P0] Zero regression tests on real historical events

The crack spread, z-score math and GARCH all claim to be production-grade, yet
no test captures behaviour on *real* historical episodes. The EIA fixtures under
`tests/fixtures/` are synthetic/static (see `conftest.py:47-69`), not
event-anchored. Missing coverage:

- **April 2020 negative WTI** — `backtest_zscore_meanreversion` must not divide
  by zero or produce `inf` PnL. Nothing in `test_quantitative_models.py:48-116`
  exercises a negative-price day.
- **OPEC+ cut 5-Oct-2022** — spread regime change; `rolling_engle_granger`
  (`test_cointegration.py:68-78`) is only tested on synthetic data.
- **COVID March-2020 inventory spike** — `forecast_depletion` is only tested
  on a linearly rising series (`test_quantitative_models.py:36-45`).

Fix: check in a gzipped CSV of Brent/WTI/EIA 2019-2024 under
`tests/fixtures/historical/`, and write six regression tests that assert the
app's current outputs on those dates. Snapshot the outputs to JSON the first
time, diff against them thereafter. This is the single highest-value addition
to the suite.

## F3 — [P0] `test_runner.py` is still the prod gate but pytest is not

`cd.yml:45-46` runs `python test_runner.py` as the "Test gate" step *before*
deploying — not `pytest`. `ci.yml:87-102` runs `test_runner.py` as the
"Legacy test_runner.py" job alongside pytest. `test_runner.py:1-17` admits it
is a belt-and-braces smoke — it only covers five modules and does not run the
E2E suite, the auth suite (9 test files under `tests/unit/test_auth_*.py`),
the guardrails (`test_trade_thesis.py:52-125`), or the cointegration/crack
modules. **A test added to `tests/unit/` today does not gate production.**

Fix: make `cd.yml:45-46` run `python -m pytest tests/unit --cov --cov-fail-under=75`
and delete the legacy runner. If you keep it, demote it to a dev-only sanity
command.

## F4 — [P1] Coverage threshold (75%) is weaker than the gate implies, and never blocks the E2E path

`pyproject.toml:56` sets `fail_under = 75`. But `ci.yml:36-41` runs pytest with
`--cov-report=term --cov-report=xml` and never passes `--cov-fail-under` on the
command line, so the threshold is enforced only by `coverage report` (which is
*not* invoked in CI). You can land a PR that drops to 50% branch coverage
without CI noticing. Also: branch coverage is enabled (`pyproject.toml:26`)
but no branch-coverage minimum is set — the 75% is line coverage only.

Fix: promote to `fail_under = 85` for lines and add `fail_under_branch = 75`;
invoke `coverage report` in CI after `pytest`.

## F5 — [P1] Flaky-test surface remains broad — three Playwright waits are still timing-sensitive

User says three flaky tests were fixed. The remaining flake surface:

- `tests/e2e/test_ui_polish_mobile.py:133` — a bare
  `page.wait_for_timeout(500)` to "let the ticker settle". This is the
  textbook anti-pattern; flake probability increases with cold-start Chromium
  on CI runners.
- `tests/e2e/test_ui_polish_sentinels.py:83-111` — `test_onboarding_toast_...`
  accepts "an iframe exists" as proof of rendering (line 107). That's a
  smoke-only check; a real regression (iframe renders blank) passes silently.
- `tests/e2e/test_dashboard_smoke.py:21-27` — two cascaded `wait_for` with
  90 s timeouts. When Streamlit is slow the test *passes slower*, not *fails
  faster*. Budget eaten silently.
- `tests/e2e/conftest.py:21-37` — `_wait_for_healthy` polls with
  `time.sleep(1)` and no jitter; under CI contention this can race with the
  kernel's port-binding.

Fix: replace `wait_for_timeout(500)` with an event-based wait (e.g. wait for
a specific DOM mutation). Make every `wait_for` have a tight timeout (≤10 s)
so flakes surface as failures, not 90 s stalls.

## F6 — [P1] Non-determinism from `pd.Timestamp.utcnow()` in the code-under-test leaks into tests

`conftest.py:84-85`, `test_coverage_gaps.py:281-282` and
`test_thesis_context_full.py:21` all build `pricing_res` using
`pd.Timestamp.utcnow()` — meaning the fixture state depends on wall-clock.
Worse, `thesis_context.py:192` computes `eia_next = _next_wednesday(today)`
from `pd.Timestamp.utcnow()` inside `build_context`. The test at
`test_thesis_context.py:48-52` constructs its own Wednesday but
`test_thesis_context_full.py:23-43` does not — `ctx.next_eia_release_date`
is literally whatever the test host's clock says on the day.

There is no `freezegun` in `requirements.txt`. The session-date in this
environment reminder (2026-04-22) is a live dependency in the test suite.

Fix: add `freezegun>=1.5`, freeze every `build_context` test to a known
instant, and add a unit test that asserts `build_context` with a frozen
`today` produces the expected `next_eia_release_date` deterministically.

## F7 — [P1] Mocks-vs-integration balance is badly skewed toward mocks for the quant stack, and skewed toward integration for CI speed

The quant modules are covered almost exclusively by tiny synthetic frames
(40-600 rows, one seed each): `test_cointegration.py:10-93` — every test uses
a one-shot `np.random.default_rng(n)`. This makes the tests *correct* but
*narrow*.

Meanwhile the slow path is paid repeatedly: six E2E files each spawn a full
`streamlit run app.py` via the session fixture at `tests/e2e/conftest.py:67-79`
— one per worker. Each E2E test bakes in a 60-180 s timeout
(`test_hero_band.py:7`, `test_ui_polish_mobile.py:32`,
`test_ui_polish_sentinels.py:15`). Total wall-clock on a green run ≈ 10-15 min
for a suite that asserts mostly DOM presence.

Fix: invert the balance. Replace three of the sentinel-only E2E tests with
component unit tests against the rendered HTML string (`theme._CSS_MOBILE` is
directly testable). Add one *real* integration test that hits
`providers._eia.fetch_inventory` with `responses` stubs rather than
`conftest.py:47-69`'s brittle substring-URL matcher.

## F8 — [P1] `conftest.py`'s `eia_fixture` URL matcher is fragile

`tests/conftest.py:61-67` routes by substring match on `url`:

```
if "WCESTUS1" in url: return _R(...)
if "WCSSTUS1" in url: return _R(...)
if "W_EPC0_SAX_YCUOK_MBBL" in url: return _R(...)
return original(url, *args, **kwargs)  # falls through to real network
```

The fall-through is a landmine — if any test accidentally hits a new EIA
endpoint (say, a future diesel inventory series), it goes to the real
network without warning. The `_scrub_env` fixture (`conftest.py:26-43`)
works hard to prevent Azure OpenAI calls; there is no equivalent for HTTP.

Fix: replace `requests.get` fallthrough with `raise RuntimeError("Unmocked
URL: %s" % url)`, and switch the three fixtures to the `responses` library
which fails loudly on unrecognised URLs by default.

## F9 — [P1] No snapshot/visual-regression tests for the UI

`tests/e2e/test_ui_polish_mobile.py:111-120` writes a single
`hero_mobile.png` full-page screenshot on every run, overwriting itself,
then asserts only that the file is non-empty — **it is never compared to a
golden**. So the "screenshot test" is really a "screenshot-writes" test.

Real snapshot testing would catch:
- CSS regressions in `_CSS_MOBILE` (hero card layout drift)
- Accidental stance-pill colour inversion
- Broken font-loading fallback

Fix: use `playwright-visual` or `pytest-playwright-snapshot`. Treat
`hero_mobile.png`, `hero_desktop.png`, `dashboard_tab1.png` as goldens
under `tests/e2e/__snapshots__/` and diff on every run. Separately,
snapshot the `THESIS_JSON_SCHEMA` structure as a fixture — today's test
at `test_trade_thesis.py:10-19` asserts keys but not the full shape, so
a subtle schema drift (new required field, changed type) slips through.

## F10 — [P2] No fuzz harness for the JSON-parsing paths that *do* see untrusted input

The LLM streaming / retry paths in `trade_thesis.py` parse JSON from model
output. Today `test_trade_thesis.py:315-354` covers one malformed→valid retry.
Real LLM output can be: truncated mid-string, trailing commas, nested
Unicode, stray markdown code fences, `NaN`/`Infinity` literals
(invalid JSON but common). The `_clamp` helper in `app.py` is well-covered
(`test_input_hardening.py:23-44`, including NaN/inf/non-numeric) — use that
style for the JSON parser.

Fix: add `atheris` or a simple `hypothesis` strategy that fuzzes bytes into
the JSON-extraction regex inside `trade_thesis.py` for 30 seconds per CI
run. Log failures to the CI artifacts bundle.

## F11 — [P2] Test naming is inconsistent and the `unit/` tree conflates layers

`tests/unit/` holds everything from schema tests (`test_trade_thesis.py:10`)
to GitHub-Actions-file sanity (`test_workflows.py:11-14`) to HTML template
placeholder checks (`test_webgpu_components.py:8-12`). That's fine for a
small project but the naming doesn't reflect the split: `test_coverage_gaps.py`
is a catch-all ("targeted coverage-gap tests") that duplicates happy-path
coverage already present in `test_provider_impls.py` (compare
`test_coverage_gaps.py:73-97` to `test_provider_impls.py:62-80`).

Fix: split into `tests/unit/math/`, `tests/unit/providers/`, `tests/unit/ui/`,
`tests/contract/` (schema + workflow-file tests), `tests/integration/`. Rename
`test_coverage_gaps.py` to the module it actually covers and delete the
duplication.

## F12 — [P2] Missing negative-path coverage on auth

`tests/unit/test_auth_session.py` covers cache-hit, mock-env, prod-lockout,
and OIDC happy path (lines 67-163). Gaps:

- No test for an OIDC claim with `sub` missing / `email` missing (`auth/session.py`
  presumably upserts on claim shape — regression bait).
- `test_auth_session.py:91-95` verifies MOCK_AUTH_USER is ignored in prod,
  but no test exercises the case where `STREAMLIT_ENV` is set to an unknown
  value like `"staging"` — does it behave like dev or prod? The code
  answers; no test locks it in.
- No test for concurrent `current_user()` calls (the cache at
  `test_auth_session.py:147-163` is single-threaded).

---

## Summary — priority order

1. **P0** F1 property tests on the quant math (biggest correctness lever).
2. **P0** F2 historical-event regression tests.
3. **P0** F3 pytest-as-the-prod-gate (fixing this is a 5-line `cd.yml` change).
4. **P1** F4 coverage threshold enforcement.
5. **P1** F5 + F6 remove `wait_for_timeout` and non-determinism.
6. **P1** F7 + F8 rebalance mocks/integration; harden `eia_fixture`.
7. **P1** F9 real snapshot testing.
8. **P2** F10-F12 polish.

Of ~47 test files, coverage is good on the *happy path* (~75% line), but the
shape of the suite — synthetic-seed math, `test_runner.py` as prod gate,
screenshot-without-golden, wall-clock-coupled fixtures — masks a real
resilience gap. The quant module is the product; it deserves the rigour the
UI currently gets.
