# Review #17 — Comprehensive Testing & Security Audit

Date: 2026-05-02
Reviewer: Cowork audit pass (read-only)
Scope: Full repo — backend FastAPI app, providers, Next.js SWA frontend,
GitHub Actions CI/CD, deployed Azure infra (oil-price-tracker RG).

> Read-only audit. No source files were modified. Findings are filed as
> GitHub issues with `tier-1` / `tier-2` / `tier-3` labels. Secrets that
> exist on disk are referenced only by env-var name; nothing is
> reproduced verbatim.

Build under audit: branch `feat/use-data-quality-hook` at `ba84bcb`,
deployed prod head `oil-tracker-api-canadaeast-0f18` + SWA
`delightful-pebble-00d8eb30f.7.azurestaticapps.net`.

---

## TL;DR — verdict: **NEEDS-ATTENTION**

The codebase has solid bones — backend coverage is 78%, gitleaks is clean
across the entire 336-commit history, the rate-limiter on
`/api/positions/execute` works in production, SWA security headers are
exemplary. **But** three production-impacting gaps deserve immediate
attention:

1. **Synthetic monitor has been failing 100% of runs for at least 12
   consecutive hours** — the canary that's meant to page on prod
   regressions is itself broken. The `/api/thesis/generate` response
   isn't valid JSON for the `record` step's `jq`. Anyone watching this
   workflow has been paged through alert fatigue or — worse — has
   tuned it out.
2. **`main` branch is not protected.** Any push goes straight in
   without a required-checks gate. CI passing is convention, not
   enforcement.
3. **CD pipeline only runs `python -c "from backend.main import app"`
   as its "test gate"** — pytest does NOT run before backend deploys.
   Coverage is 78% in CI but production ships on a smoke import.

E2E coverage is zero (Playwright dep is in `package.json` but no
config, no tests, no CI step). Property-based testing is zero. These
are the next-tier gaps to close.

---

## Section 1 — Testing setup

### 1.1 Coverage scorecard

**Backend** (root + backend/, run as `pytest tests/unit tests/regression`
to mirror CI): **78.28%** statements / branch — passes the 75%
`fail_under` floor.

| Module | Cover | Below 70%? |
|---|---|---|
| `quantitative_models` | 83% | — |
| `trade_thesis` | 89% | — |
| `thesis_context` | 89% | — |
| `cointegration` | 88% | — |
| `data_ingestion` | 86% | — |
| `crack_spread` | 72% | — |
| `vol_models` | 95% | — |
| `alerts` | 64% | **yes** |
| `observability` | 43% | **yes** |
| `providers/_aisstream` | 23% | **yes** |
| `providers/_databento` | 35% | **yes** |
| `providers/_fred` | 51% | **yes** |
| `providers/_eia` | 66% | **yes** |
| `providers/health` | 67% | **yes** |
| `providers/_polygon` | 90% | — |
| `providers/_twelvedata` | 88% | — |
| `providers/_yfinance` | 77% | — |
| `providers/_cftc` | 86% | — |
| `providers/news_rss` | 74% | — |
| `providers/ofac` | 89% | — |
| `providers/inventory` | 86% | — |
| `providers/pricing` | 81% | — |

`backend/` services + routers were excluded from this run because
`backend/tests/test_data_quality_wiring.py` registers an `asyncio`
marker that the root `pyproject.toml`'s `--strict-markers` rejects.
That mis-config means `backend/` modules don't show up in the
coverage table — separate finding (issue filed).

**Frontend** (vitest --coverage v8, 116 tests across 24 files):
**59.75%** statements / **55.6%** branches / **69.06%** functions /
**62.61%** lines. Below the unwritten 70% bar on statements.

| File | Cover |
|---|---|
| `components/illustrations/EquityCurveFlat.tsx` | **0.0%** |
| `components/illustrations/SpreadCurvesIllustration.tsx` | **0.0%** |
| `components/globe/FleetGlobe.tsx` | **7.0%** |
| `lib/use-global-shortcuts.ts` | **19.0%** |
| `components/globe/VesselPanel.tsx` | **33.3%** |
| `lib/sse.ts` | **43.8%** |
| `components/common/ChartErrorBoundary.tsx` | **44.4%** |
| `components/hero/TradeIdeaHeroClient.tsx` | **54.4%** |
| `components/common/EmptyState.tsx` | 58.3% |
| `components/hero/HeroBackground.tsx` | 64.5% |
| `components/data-quality/DataQualityTile.tsx` | 68.8% |
| `components/track-record/CalibrationChart.tsx` | 68.8% |
| `components/charts/SpreadChart.tsx` | 75.9% |
| `components/charts/InventoryChart.tsx` | 95.0% |
| `components/charts/StretchChart.tsx` | 95.8% |
| `components/charts/BacktestChart.tsx` | 90.6% |
| `components/hero/InstrumentTile.tsx` | 94.7% |
| `components/hero/ConfidenceBar.tsx` | 84.2% |
| `components/hero/StancePill.tsx` | 100% |

The hero is well-tested (most files >80%). Charts are well-tested.
The globe is the gap — rendering-heavy code mocked away with a WebGPU
shim, so the actual globe component clocks 7%. SSE plumbing is
under-covered too — the path through `lib/sse.ts` that the synthetic
monitor exercises in prod has no unit test.

### 1.2 E2E coverage matrix

There are no E2E tests. `frontend/tests/e2e/` does not exist. The
`@axe-core/playwright` package is installed and `__tests__/a11y.test.tsx`
references a `tests/e2e/` directory in a comment — but that directory
was never created and there is no `playwright.config.ts`, no Playwright
fixture, no Playwright step in any workflow.

| Critical user path | E2E test exists? |
|---|---|
| Land on home, hero renders with stance + confidence + 3 instruments + 5-item checklist + plain-English headline | **NO** |
| Generate new thesis via SSE, verify tokens stream + final shape | NO |
| Execute paper trade from Tier-2 ETF instrument, verify order fires + appears in positions panel | NO |
| `/macro` page — all charts render with non-empty series | NO |
| `/fleet` — globe renders + vessels visible | NO |
| `/positions` — Alpaca paper account data populates | NO |
| `/track-record` — calibration verdict + Brier render with real numbers | NO |
| Move dislocation alert slider, verify chart updates | NO |
| Toggle advanced view, verify additional tooltips/labels appear | NO |
| Mobile viewport (iPhone 13) — every above path renders without horizontal scroll | NO |

Mitigations today: (a) the synthetic-thesis-monitor cron does an
end-to-end probe of the SSE thesis path every 22 minutes — though it
itself is broken right now (§1.4); (b) the unit suite does mount each
component under jsdom + axe-core. Neither replaces real-browser
integration.

### 1.3 Property-based testing audit

Zero. `grep -rn "from hypothesis|@given|hypothesis.strategies"` against
`backend/`, `tests/`, `providers/` returns nothing. No `hypothesis`
entry in either `requirements.txt`. Concrete invariants worth
property-testing that have no coverage:

- `quantitative_models.compute_spread_zscore` — z-score of a constant
  series should be 0 (or NaN, deterministically).
- `cointegration` — `cointegrated(a, b)` should equal `cointegrated(b, a)`
  modulo sign of the spread.
- `quantitative_models.compute_half_life` — should be positive and
  finite for any real mean-reverting AR(1) process.
- `quantitative_models.simulate_inventory` — Monte Carlo mean across N
  paths should converge to the analytical mean as N grows.
- `backtest.run` — equity curve should be monotonically non-decreasing
  across the subset of locked profitable trades.

### 1.4 Regression corpus check

`tests/regression/known_scenarios.jsonl` exists and contains exactly
**20 scenarios** (matches the issue #104 spec).
`tests/regression/test_known_scenarios.py` is wired into CI via
`pytest tests/unit tests/regression`. Pass.

### 1.5 Synthetic monitor verification

**FAIL.** The `synthetic-thesis-monitor` workflow runs every 22m on
schedule. It has failed 12/12 times in the last 60 GH-Action runs
(every single recent invocation). Root cause from
`gh run view --log-failed`:

```
jq: parse error: Invalid numeric literal at line 1, column 6
##[error]Process completed with exit code 5.
```

The cron POSTs to `/api/thesis/generate` and tries to extract
`.consecutive_failures` from the `/api/synthetic/record` response,
but the response body isn't JSON in the expected shape. Either the
record endpoint changed shape, the curl is failing silently and the
fallback `{"consecutive_failures":-1}` literal is being interpreted
weirdly by `jq`, or the SSE consumer is leaving a non-JSON tail in
the buffer. **This is the canary — it must be repaired or muted.
A canary that always pages teaches everyone to ignore the page.**

### 1.6 CI gates summary

| Workflow | Trigger | Hard gate? | What it runs |
|---|---|---|---|
| `ci.yml` | push/PR to main | yes (PR check) | pytest + coverage on Python 3.11 + 3.12 (matrix). `tests/unit + tests/regression`. |
| `ci-nextjs.yml` | push to non-main / PR (paths: backend, frontend) | yes (PR check) | Backend: smoke import only. Frontend: `npm ci --legacy-peer-deps`, typecheck, lint, vitest, build. |
| `cd-nextjs.yml` | push to main / feat-branches | deploy gate | **Backend: smoke import ONLY — pytest does NOT run before deploy.** Frontend: build then deploy. |
| `security-scan.yml` | push/PR/Mon 05:00 UTC | yes | bandit `-ll -ii`, pip-audit `--strict`, npm audit `--audit-level=high`. |
| `codeql.yml` | push/PR | yes | GitHub CodeQL Python+JS scan. |
| `synthetic-thesis-monitor.yml` | schedule */22min | no (alerting) | Probes prod thesis SSE; **currently broken**. |
| `silence-detector.yml` | schedule | no | Probes for stalled streams. |
| `keep-warm.yml` | schedule | no | Hits `/health` to prevent App Service cold start. |
| `monthly-calibration.yml` | schedule monthly | no | Calibration drift check. |
| `monthly-lighthouse.yml` | schedule monthly | no | Lighthouse perf on SWA. |

**Critical gap**: `gh api repos/Aidan2111/macro-oil-terminal/branches/main/protection`
returns **404 Branch not protected**. CI passes are advisory only. A
push directly to main bypasses every gate above.

### 1.7 Slow / flaky / non-deterministic test inventory

**Slow tests (>0.5s)**: none. Slowest unit is
`test_monte_carlo_percentiles_monotone` at 0.42s. Slowest 20 are all
≤0.42s. Healthy.

**Flaky tests in last 60 CI runs**: none. The only failing workflow is
`synthetic-thesis-monitor` (12/12 fail, but that's external-API broken,
not flake).

**Non-deterministic markers**: the `pyproject.toml` declares `slow`,
`network`, and `live_llm` markers; CI runs without `network` or
`live_llm` so live network tests don't run by default. The vitest
suite emits two `act()` warnings on `PositionsView` — not failing,
but the warnings indicate state updates outside `act()` which can
cause timing flake under load.

---

## Section 2 — Security review

### 2.1 SAST

**bandit `-r backend/ providers/ -ll`**: clean. 0 medium+ findings.
158 low-severity / high-confidence findings (try/except/pass on
backoff loops and broad `except Exception` in `_provider_error`) —
all reviewed in #14 and intentional.

**semgrep**: not run in this pass (sandbox time budget). The Wave-4
review #14 noted the same — recommendation stands to wire semgrep
into a hosted GH-Actions job (no time ceiling there).

**eslint-security plugin**: not installed. The `next lint` gate
catches a subset (no-eval, no-implied-eval, etc.). Adding
`eslint-plugin-security` would catch additional categories
(detect-non-literal-fs-filename, detect-object-injection, etc.).

### 2.2 Dependency audit

| Tool | Scope | Result |
|---|---|---|
| `pip-audit -r requirements.txt` (Python 3.13 venv) | runtime + dev | **0 vulns** |
| `pip-audit -r backend/requirements.txt` | backend deploy bundle | **0 vulns** |
| `npm audit` | frontend, full tree | 0 critical, 0 high, **2 moderate** |

Moderate findings: `postcss <8.5.10` XSS via unescaped `</style>`
([GHSA-qx2v-qp2m-jg93](https://github.com/advisories/GHSA-qx2v-qp2m-jg93)),
pulled transitively via `next`. The published fix path is
`npm audit fix --force` which downgrades `next` to `9.3.3` — a
breaking change. Not actionable until next-stable
gets a non-vulnerable postcss bump. Tracked in `SECURITY.md` already.

### 2.3 Secrets scan (full git history)

**`gitleaks detect --source .`**: 336 commits scanned, 20.79 MB —
**no leaks found**. History is clean.

**`gitleaks detect --no-git`** (working tree, including untracked):
12 matches, all in gitignored paths:
- `.env` lines 38, 39, 41, 44 — local development env (gitignored)
- `frontend/.next/cache/*`, `frontend/.next/prerender-manifest.json`,
  `frontend/.next/server/server-reference-manifest.json` — build cache
  (gitignored)
- `.venv/share/jupyter/nbextensions/pydeck/index.js.map` — virtualenv
  artifact (gitignored)

None of these have ever been committed. Pass.

### 2.4 SWA security headers — `curl -I https://delightful-pebble-00d8eb30f.7.azurestaticapps.net/`

| Header | Status |
|---|---|
| `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload` | OK |
| `Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://threejs.org; connect-src 'self' https://oil-tracker-api-canadaeast-0f18.azurewebsites.net wss://stream.aisstream.io; frame-ancestors 'none'; base-uri 'self'` | present but `'unsafe-inline'` for both script and style |
| `X-Frame-Options: DENY` | OK |
| `X-Content-Type-Options: nosniff` | OK |
| `Referrer-Policy: strict-origin-when-cross-origin` | OK |
| `Permissions-Policy: camera=(), microphone=(), geolocation=()` | OK |
| `X-XSS-Protection: 1; mode=block` | OK (legacy, but harmless) |
| `X-DNS-Prefetch-Control: off` | OK |

PR #15's `globalHeaders` are deployed and serving correctly. The only
gap is the `'unsafe-inline'` allowance in CSP — a moderate risk
because Next.js's static export inlines hydration data. Path forward:
nonce-based CSP via Next 15's `headers()` middleware, or SHA-256
allowlist of known inline scripts.

**API security headers** (`curl -I https://oil-tracker-api-canadaeast-0f18.azurewebsites.net/api/positions/execute`):
- `Strict-Transport-Security`: **missing**
- `Content-Security-Policy`: **missing**
- `X-Frame-Options`: **missing**
- `X-Content-Type-Options`: **missing**

The API is reached directly from the browser via the SWA's
`connect-src`, so missing headers on the API leak less than they
would on the SWA — but a defense-in-depth fix is to set them in a
`SecurityHeadersMiddleware` in `backend/main.py`. Moderate finding.

### 2.5 Rate-limit verification on `/api/positions/execute`

Spammed 6 POSTs in <1s from one IP:

```
422 0.385s (validation: symbol/qty/side invalid — first one consumed the 1-req slot)
429 0.380s {"detail":"Execute rate limit: 1 request per 2s."}
429 0.356s
429 0.361s
429 0.364s
429 0.369s
```

After a 3-second sleep, a single request returned 422 again, and an
immediate follow-up returned **429 with `retry-after: 2`** in the
response headers. The dual-gate (1 req/2s + 30 req/5min) introduced
in PR #15 is intact and surviving subsequent merges. Pass.

### 2.6 Azure RBAC + secrets review

`az role assignment list --assignee 9d8ae4e7-d5f1-49cc-b6e3-b62cf1ad23a8 --all`:

```
Principal                             Role         Scope
------------------------------------  -----------  ---------------------------------------------------------------------------
9d8ae4e7-d5f1-49cc-b6e3-b62cf1ad23a8  Contributor  /subscriptions/5ae389ef-.../resourceGroups/oil-price-tracker
```

The OIDC service principal has Contributor scoped to the
`oil-price-tracker` resource group only — appropriate least-privilege
for a single-app deployment. Could be tightened further to specific
resource Contributor (e.g., Web Contributor on the App Service) but
the current scope is defensible.

Secrets in source: every reference to `AISSTREAM_API_KEY`,
`ALPACA_API_SECRET`, `DATABENTO_API_KEY`, `EIA_API_KEY`,
`AZURE_OPENAI_KEY` is via `os.environ.get(...)`. Zero hardcoded
secrets. `.env` is gitignored (`.env`, `.env.*` patterns both
present in `.gitignore`).

### 2.7 Auth state — undocumented choice

The product is a single-user demo. There is no authentication on any
endpoint. `/api/positions/execute` has an
`ALPACA_PAPER === 'true'` env-gate + Origin allowlist + rate limit,
but there is no user identity. This is a deliberate design choice
but is not documented anywhere. A new contributor (or future-Aidan)
won't know whether this is "we'll add auth later" or "we never want
auth here." Filing follow-up to write `docs/security/auth-stance.md`.

### 2.8 Input validation audit

POST endpoints in `backend/main.py`:

| Path | Validator | Verdict |
|---|---|---|
| `/api/thesis/generate` | `_validate_thesis_body` — type+enum+positive checks | OK (returns 422) |
| `/api/thesis/regenerate` | delegates to `/generate` | OK |
| `/api/thesis/generate/fixture` | none — debug-only | OK (no body) |
| `/api/backtest` | none on body — direct dict pass-through | **gap** |
| `/api/backtest/fixture` | none — fixture | OK |
| `/api/positions/execute` | hand-rolled — symbol/qty/side/type/tif/limit_price | OK (returns 422 with clean detail) |
| `/api/synthetic/record` | wraps `SyntheticRun` Pydantic model in service | OK |

`/api/backtest` accepts an arbitrary dict and forwards it to the
backtest engine. Engine itself does its own validation, but a
malformed body propagates exception text into the
`_provider_error` response. Recommend converting to Pydantic
`BaseModel` for parity with the synthetic recorder.

### 2.9 Log hygiene audit

`az webapp log download` → 1.7 MB zip → grep for `key|secret|token|bearer|authorization`
filtered against placeholder/REDACTED noise: **no matches**.

The codebase's log-emission policy (verified in review #14 §3) is
intact: no `log.info(api_key)` style emission, no exception-message
echo of secrets, App Insights instrumentation only emits sanitized
fields. Pass.

---

## Section 3 — Verdict + prioritized backlog

### Overall: **NEEDS-ATTENTION**

Healthy on dependency hygiene, secrets hygiene, headers (SWA-side),
and rate-limit enforcement. Three Tier-1 gaps demand action this week.
The Tier-2 list is the test-quality work that will move this to
HEALTHY.

### Tier-1 — must fix this week

1. **Synthetic monitor failing 100% of runs.** Either the
   `/api/thesis/generate` response shape changed or the `jq`
   parse is fragile. Repair or temporarily mute (better: repair) so
   the canary recovers signal.
2. **`main` is not a protected branch.** Enable required PR review +
   required status checks (CI, CI-nextjs, security-scan, codeql) +
   no force-push.
3. **CD pipeline runs only `from backend.main import app` as the test
   gate.** Backend deploys without pytest. Add a `pytest tests/unit
   tests/regression` step to `cd-nextjs.yml` before the package
   step.

### Tier-2 — this sprint

4. **Zero E2E tests.** Wire up Playwright with the 10 critical paths
   from §1.2. Run as a non-blocking CI job first; promote to required
   once green.
5. **Zero property-based tests.** Add `hypothesis` to `requirements.txt`
   and write the 5 invariants from §1.3 (z-score-of-constant,
   cointegration symmetry, half-life positivity, MC mean
   convergence, equity-curve monotonicity).
6. **Frontend coverage gaps**: `FleetGlobe.tsx` 7%, `lib/sse.ts` 44%,
   `ChartErrorBoundary` 44%, `TradeIdeaHeroClient` 54%, illustrations 0%.
7. **Backend coverage gaps**: `observability` 43%, `providers/_aisstream`
   23%, `providers/_databento` 35%, `providers/_fred` 51%.
8. **CSP allows `'unsafe-inline'` for script + style.** Move to nonce
   or hash-based allowlist.
9. **Auth stance undocumented.** Write `docs/security/auth-stance.md`
   with the deliberate "no authn — single-user demo" choice and the
   migration paths (Clerk, Supabase Auth) for when multi-user is
   wanted.

### Tier-3 — cleanup

10. **`/api/backtest` accepts arbitrary dict.** Wrap in Pydantic
    `BaseModel` for parity with synthetic recorder.
11. **API service missing security headers.** Add `SecurityHeadersMiddleware`
    in `backend/main.py` (HSTS, X-Content-Type-Options, X-Frame-Options).
12. **`backend/tests/test_data_quality_wiring.py` registers `asyncio`
    marker that root pyproject's `--strict-markers` rejects** —
    backend service tests excluded from main coverage run.
13. **PositionsView tests emit `act()` warnings** — wrap state updates
    properly to prevent timing flake.
14. **2 moderate npm advisories (postcss via next).** Reconfirm in
    SECURITY.md, retest each `next` minor.
15. **Add `eslint-plugin-security`** to the frontend lint gate.
16. **CodeQL is enabled but findings dashboard not surfaced** — add
    a weekly summary to the audit doc cadence.
17. **`semgrep --config=auto` not in CI.** Add as nightly job (no
    sandbox time pressure on hosted runners).

---

## Sources / artefacts captured during this audit

- `/tmp/pytest-coverage.log` — pytest run, 78.28% coverage, 520 passed.
- `/tmp/coverage-frontend/coverage-summary.json` — vitest v8 coverage.
- `/tmp/bandit.json`, `/tmp/bandit-human.log` — bandit `-ll` clean.
- `/tmp/pip-audit-root.log`, `/tmp/pip-audit-backend.log` — clean.
- `/tmp/npm-audit.json` — 2 moderate, 0 high+.
- `/tmp/gitleaks.json` (history, clean), `/tmp/gitleaks-current.json`
  (12 matches all in gitignored paths).
- `/tmp/swa-headers.txt` — full SWA response headers.
- `/tmp/api-logs/` — unzipped App Service logs, no secret leaks.

---

Reviewer note: this audit overlaps with review #14 on the
security-tooling sweep but extends it with (a) the testing-setup
audit it didn't cover, (b) a fresh dependency / SAST / secrets
re-run on the post-Wave-4 codebase, and (c) verification that
PR #15's hardening landed and is still serving correctly in
production.
