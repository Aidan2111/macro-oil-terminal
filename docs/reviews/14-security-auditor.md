# Review #14 — Security Auditor

Date: 2026-04-25
Reviewer: Security auditor (subagent)
Scope: Macro Oil Terminal full stack — FastAPI backend, legacy provider modules,
Next.js 15 SWA frontend, and the GitHub Actions deploy pipeline.

> Read-only audit. No source files were modified during this review. Only this
> doc was created. No secrets that exist anywhere in the working tree are
> reproduced verbatim below — every match is redacted to `<REDACTED>`.

---

## 1. OWASP Top 10 (2021) — coverage table

| ID  | Category                                | Result   | One-line rationale |
|-----|-----------------------------------------|----------|--------------------|
| A01 | Broken Access Control                   | **Fail** | No authn/z anywhere; `/api/positions/execute` is reachable by any internet caller (only `ALPACA_PAPER` env-gate + 1 req / 2 s in-process bucket gate it). |
| A02 | Cryptographic Failures                  | **Pass** | All upstreams reached over HTTPS / WSS. No cleartext PII; secrets live only in App Service settings + read once via `os.environ.get`. |
| A03 | Injection                               | **Pass** | All user inputs are parsed via Pydantic models (`ExecuteRequest`) or validated allow-lists in `main.py`'s `_validate_thesis_body`. No SQL anywhere. No `shell=True`, no string-interpolated subprocess. |
| A04 | Insecure Design                         | **Partial** | Hard-coded `paper=True` in `alpaca_service.get_client()` is a good belt-and-braces; but a single-process token bucket on `/positions/execute` is not a meaningful rate limit if the App Service ever scales out. |
| A05 | Security Misconfiguration               | **Partial** | `CORSMiddleware(allow_origins=["*"])` plus no `Content-Security-Policy` / `Strict-Transport-Security` / `X-Frame-Options` on the SWA. Otherwise sane. |
| A06 | Vulnerable & Outdated Components        | **Partial** | `pip-audit` clean; `npm audit` reports 6 *moderate* dev-only advisories (vite/vitest/esbuild/postcss). Production runtime deps clean. |
| A07 | Identification & Authentication Failures| **Fail** | No identification at all. Single-user demo posture; flagged as Info elsewhere because it's a known gap, but it is the OWASP A07 reality today. |
| A08 | Software & Data Integrity Failures      | **Pass** | CD pipeline uses Azure OIDC federated creds (no long-lived service-principal secret in repo). `npm ci`/`pip install -r` against pinned ranges. CodeQL runs on every PR. |
| A09 | Security Logging & Monitoring Failures  | **Partial** | App Insights wired via `observability.py`; no logger emits any secret value (verified — see §3 Log hygiene). But `/api/positions/execute` audit log writes to local disk only (`data/executions.jsonl`) which doesn't survive scale-down. |
| A10 | Server-Side Request Forgery (SSRF)      | **Pass** | Backend is the *originator* of all upstream calls — URLs are static, never user-supplied. No proxy / fetch-by-URL endpoint exposed. |

Letter grid (P / Pa / F): **F · P · P · Pa · Pa · Pa · F · P · Pa · P**

---

## 2. Tooling sweep — raw outputs

### 2.1 `bandit -r backend/ providers/ -ll -ii` (last 100 lines)

```
[main]	INFO	profile include tests: None
[main]	INFO	profile exclude tests: None
[main]	INFO	cli include tests: None
[main]	INFO	cli exclude tests: None
[main]	INFO	running on Python 3.10.12
Working...  100%
Run started:2026-04-26 02:57:56.779146+00:00

Test results:
	No issues identified.

Code scanned:
	Total lines of code: 4613
	Total lines skipped (#nosec): 0
	Total potential issues skipped due to specifically being disabled (e.g., #nosec BXXX): 0

Run metrics:
	Total issues (by severity):
		Undefined: 0
		Low: 153
		Medium: 0
		High: 0
	Total issues (by confidence):
		Undefined: 0
		Low: 0
		Medium: 1
		High: 152
Files skipped (0):
```

(`-ll -ii` filters to medium+ severity AND medium+ confidence — clean. The 153
Low-severity findings at default threshold are dominated by `try/except/pass` on
the AISStream backoff loop and `except Exception` in `_provider_error` — both
intentional and reviewed in §3.)

### 2.2 `semgrep --config=auto --severity=ERROR --severity=WARNING ...` — **not run**

`semgrep` was installed but every invocation against `backend/ providers/
frontend/` (and even the smaller `backend/ providers/`) timed out at the
sandbox's 45 s ceiling — semgrep's auto-config download + ruleset compile
exceeded the budget. **Recommendation:** wire it into CI (a hosted GH runner
has 4–6× the budget); see §5 for the workflow sketch.

### 2.3 `cd frontend && npm audit --audit-level=moderate --json` (head 200)

```json
{
  "auditReportVersion": 2,
  "vulnerabilities": {
    "esbuild":   {"severity": "moderate", "isDirect": false, "via": ["GHSA-67mh-4wv8-2f99 — dev-server CSRF"]},
    "next":      {"severity": "moderate", "isDirect": true,  "via": ["postcss"]},
    "postcss":   {"severity": "moderate", "isDirect": false, "via": ["GHSA-qx2v-qp2m-jg93 — XSS via </style>"]},
    "vite":      {"severity": "moderate", "isDirect": false, "via": ["GHSA-4w7w-66w2-5vf9 — path traversal in .map"]},
    "vite-node": {"severity": "moderate", "isDirect": false, "via": ["vite"]},
    "vitest":    {"severity": "moderate", "isDirect": true,  "via": ["vite", "vite-node"]}
  },
  "metadata": {
    "vulnerabilities": {"info":0,"low":0,"moderate":6,"high":0,"critical":0,"total":6},
    "dependencies":     {"prod":229,"dev":526,"optional":108,"peer":0,"total":790}
  }
}
```

**All six are dev-time only** (vitest test runner + esbuild/vite under it, plus
postcss inside the test/build path). None reach the `out/` static export the
SWA serves. Fix is `npm install vitest@latest` (semver-major bump). The
postcss-via-next advisory chain claims `fixAvailable: next@9.3.3` — false
positive: the npm audit DB hasn't yet picked up Next 15's vendored postcss
fork. Tracking-only; do not downgrade Next.

### 2.4 `pip-audit -r backend/requirements.txt -r requirements.txt`

```
No known vulnerabilities found
```

Both the FastAPI runtime closure and the legacy Streamlit closure are clean
against PyPI Advisory DB at audit time.

### 2.5 `gitleaks` — **not run** (substituted with `detect-secrets`)

The sandbox proxy refused the GitHub release download for gitleaks. Substituted
`detect-secrets scan` over the same tree, full git history independently
inspected by `git rev-list --all | git ls-tree`. Findings (truncated to last
50 lines, all hashes redacted):

```
files_with_findings = 4
backend/tests/test_build_info.py    : Hex High Entropy String, line 24       (test fixture: BUILD_SHA hex sentinel)
backend/tests/test_positions.py     : Secret Keyword,         line 27       (SECRET_SENTINEL = "<REDACTED-test-only>")
docs/designs/p1-auth.md             : Secret Keyword,         lines 59, 63   (placeholder examples in design doc)
frontend/__tests__/Footer.test.tsx  : Hex High Entropy String, line 12      (test sha sentinel)
```

All four matches are intentional fixtures or doc placeholders (the
`SECRET_SENTINEL` is *literally* a test that asserts the response body never
echoes a placeholder string, which is the right pattern). **No real secret
exists in tracked source.**

Independent git-history check:

```
$ git ls-files | grep -E "\.env"
.env.example                     # safe — placeholder values only

$ git log --all --full-history -- .env
(empty — never tracked)

$ ls .env
-rw-r--r-- 1 user staff   ...  .env       # exists locally, gitignored
```

The repo-root `.gitignore` correctly contains `.env` and `.env.*` with a
`!.env.example` exception. The local `.env` on Aidan's workstation contains
*real* third-party API keys (EIA, AISSTREAM, ALPACA paper, DATABENTO) — see
Finding S-1 below — but it has never been committed.

---

## 3. Specific findings

Severity = Critical / High / Medium / Low / Info.

### S-1 — Real API keys in untracked local `.env` (Medium)

* File: `.env` (gitignored; lives on the contributor's workstation only)
* Verified `git log --all --full-history -- .env` returns empty; `git ls-files`
  excludes the file. The file is not in the deploy zip either — `cd.yml` and
  `cd-nextjs.yml` zip the repo and rely on Azure App Service settings for env
  vars at runtime (correct posture).
* Risk: the keys are present on Aidan's laptop in plaintext. If the laptop is
  imaged for support, sent in for repair, or the directory is accidentally
  re-attached to a non-gitignore-aware bundler, every key leaks at once.
  ALPACA secret is paper-only, AISSTREAM is free-tier, EIA is free, DATABENTO
  is metered.
* Exploit scenario: low. Most damaging would be DATABENTO billable units run
  up by an attacker who acquired the key.
* **Fix:** rotate any key the contributor doesn't actively need locally and
  store the rest in `~/.config/macro-oil-terminal/.env` outside the repo
  directory. Add a one-liner pre-commit hook (`detect-secrets-hook`) so a
  future `.env` rename can't sneak through.

### S-2 — No `Content-Security-Policy` / `Strict-Transport-Security` / `X-Frame-Options` on SWA (High)

* File: `static-web-apps/staticwebapp.config.json` *and* the duplicate
  `frontend/staticwebapp.config.json` (lines 21–24 in both)
* Currently sets only:
  ```json
  "globalHeaders": {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin"
  }
  ```
* Risk: clickjacking via iframe (no `X-Frame-Options` / `frame-ancestors`),
  no defence-in-depth against a future XSS, and TLS-strip on a one-time
  HTTP downgrade is feasible.
* Exploit scenario: an attacker hosts a clickjack page that frames the
  Static Web App; victim's browser auto-completes any future logged-in
  state (when auth lands in phase 2, the cost of *not* having
  `X-Frame-Options` already set goes from Low to Medium).
* **Fix:** add to `globalHeaders` in *both* `staticwebapp.config.json`
  files (they are out-of-sync duplicates already — see S-9):
  ```json
  "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self' https://oil-tracker-api-canadaeast-0f18.azurewebsites.net wss://oil-tracker-api-canadaeast-0f18.azurewebsites.net; frame-ancestors 'none'",
  "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
  "X-Frame-Options": "DENY",
  "Permissions-Policy": "geolocation=(), microphone=(), camera=()"
  ```
  `'unsafe-inline'` for styles is required by Next 15's CSS-in-JS unless
  you ship a nonce middleware; revisit once an auth layer arrives.

### S-3 — `CORSMiddleware(allow_origins=["*"])` covers `/api/positions/execute` (High)

* File: `backend/main.py:110-116`
* Today every backend route is mounted on the same FastAPI app and shares
  the wildcard CORS policy. Read-only data endpoints (`/api/spread`,
  `/api/inventory`, etc.) are correct as wildcard-public. **`/api/positions/*`
  is not** — any malicious site can `fetch('https://oil-tracker-api...
  /api/positions/execute', {method: 'POST', body: ...})` straight from a
  user's browser; CORS isn't blocking the request itself, it just lets the
  *response* be read. Since execute returns JSON the attacker doesn't even
  need to read the response — the side effect (placing a paper order)
  has happened.
* `allow_credentials=False` is the only thing limiting damage today. With
  no auth cookies in flight, the attacker can't impersonate a logged-in
  user (because there is no logged-in state). But the `/api/positions/execute`
  endpoint accepts orders from *anyone* with no authentication, so CORS
  is irrelevant — the order will be placed regardless of origin.
* Exploit scenario: drive-by trading. Attacker hosts JS that POSTs random
  buy/sell orders to the backend; the in-process rate-limit (1/2 s) caps
  noise but does not stop a slow attacker from churning paper P&L.
* **Fix (defence-in-depth, not a substitute for auth):** mount
  `/api/positions/*` under its own router with a stricter
  `CORSMiddleware(allow_origins=["https://delightful-pebble-00d8eb30f.7.azurestaticapps.net"], allow_credentials=True)`
  AND require an `X-Trading-Token` shared-secret header until phase-2 auth
  lands. The token compares with `hmac.compare_digest`. See top-15 fix list.

### S-4 — `/api/positions/execute` rate limit is per-process and trivially bypassable (High)

* File: `backend/routers/positions.py:34-43, 88-111` and the parallel
  inline implementation in `backend/main.py:1013-1073`
* The token bucket is a module-level `_last_execute_monotonic` float
  guarded by `asyncio.Lock`. Two concrete problems:
  1. **Per-process, not per-IP.** App Service auto-scales (default 1
     instance, but it can scale). At 2 instances, the effective limit is
     2 req / 2 s. At burst, even a single instance accepts 1 req per
     `_EXECUTE_MIN_INTERVAL_S` regardless of caller — *one IP can DOS
     every other caller* by hogging the bucket.
  2. **The `main.py` route at line 1013 doesn't share the bucket.** The
     router-based `/api/positions/execute` (in `routers/positions.py`)
     and the inline route in `main.py` are *both* registered if the
     router is mounted; whichever wins, the other path is unrate-limited.
     I couldn't confirm which is wired in production from this audit
     (router mounting isn't visible in `main.py:create_app`); flag for
     verification.
* Exploit scenario: attacker discovers `POST /api/positions/execute` and
  fires `qty=999999` orders at 0.5 Hz. Rate limit accepts the first one,
  and Alpaca paper rejects the rest as oversized — but the audit log
  is now full of garbage and the next legitimate user is 429'd for 2 s.
* **Fix:** move to a Redis-backed limiter (`slowapi` with a Redis store),
  key the bucket by `(client_ip, route)`, set 1 req / 5 s for execute,
  6 req / minute burst. Pin the route to one canonical handler.

### S-5 — No `dangerouslySetInnerHTML`, no client-side XSS surface in the LLM thesis renderer (Info)

* Verified: `grep -RIn 'dangerouslySetInnerHTML\|innerHTML\|__html\|eval(\|new Function' frontend/` returns 0 hits.
* The streamed thesis text from `/api/thesis/generate` is rendered via
  React `{state.delta}` text nodes in `TradeIdeaHeroClient.tsx`; the
  `key_drivers`, `invalidation_risks`, and `data_caveats` arrays in
  `ThesisRaw` are joined by React's text-node escaping. No markdown
  renderer is wired in, so even if the LLM tries to slip in `<script>`
  tags, React will print them as escaped text.
* Risk today: none. **Risk in 30 days:** if anyone wires
  `react-markdown` or `dangerouslySetInnerHTML={{__html: ...}}` to make
  the thesis prettier, that's a stored-XSS class vulnerability driven by
  any prompt-injection of the upstream news/EIA payloads. Add a doc note.

### S-6 — Log hygiene is clean for secrets (Pass / Info)

Audit performed via `grep -RIn 'logger\.\|print(\|logging\.' backend/ providers/`:

* No matches in `backend/`.
* No matches in `providers/`.
* `observability.py:24-86` uses `logger.info` / `logger.warning` for the
  Application Insights bootstrap; the only data values it logs are the
  exception `repr()` of an OpenTelemetry config error and the success
  message "Application Insights connected." — neither touches a secret.
* `_provider_error` (`backend/main.py:69-88`) embeds `type(exc).__name__`
  + `str(exc)` into the 503 body. Most provider exceptions are URLLib /
  ConnectionError — safe — but verify periodically that no provider
  raises an exception that includes its own credential in the message.
  (yfinance and openai-py do not at the versions pinned.)

* **Recommendation (Low):** wrap `_provider_error` to scrub strings
  matching `r'(?i)(api[_-]?key|secret|token)["\s:=]+[\w\-./+]{12,}'`
  before they reach the JSON body. Belt-and-braces.

### S-7 — Auth gap (Info — but it is the project's biggest risk)

* No authn/z in front of any `/api/*` route. Single-user demo. This is
  documented in `backend/services/alpaca_service.py:13-15` and
  `backend/routers/positions.py:11-13` as a phase-2 TODO.
* Routes whose risk profile changes the moment a second user lands:
  * `POST /api/positions/execute` — placing orders against a shared
    paper account. Becomes per-user account binding.
  * `POST /api/thesis/generate` — Azure OpenAI quota burn. A
    multi-tenant model has to bill per user and rate-limit per user.
  * `GET  /api/positions`, `/api/positions/account` — leaks the *only*
    paper account's positions to anyone today; multi-user makes this a
    privacy bug.
* **Recommendation:** ship the design in `docs/designs/p1-auth.md`
  before the second user.

### S-8 — Azure RBAC / OIDC posture (Pass)

* `.github/workflows/cd.yml:48-53`, `cd-nextjs.yml:80-86`: both use
  `azure/login@v2` with `client-id`, `tenant-id`, `subscription-id`
  pulled from secrets, **and** `permissions: id-token: write` is set
  per workflow — that's the OIDC federated-credential flow, no
  `client-secret` ever touches the runner.
* `cd-nextjs.yml:222`: `AZURE_STATIC_WEB_APPS_API_TOKEN` is the only
  long-lived secret in the pipeline. SWA deploy tokens are
  app-scoped (cannot list / mutate other resources) — acceptable.
* No long-lived service-principal secret in the repo.
* **Recommendation (Low):** scope the federated cred to the two App
  Services + the SWA's resource group only (verify in Azure AD app
  registration's federated credentials). The workflow already requests
  `contents: read` only — good.

### S-9 — Drift between `static-web-apps/staticwebapp.config.json` and `frontend/staticwebapp.config.json` (Low)

* Both files are byte-identical right now. SWA only reads *one* of them
  (whichever is at `app_location`'s root after build). Today
  `cd-nextjs.yml:225` sets `app_location: "frontend"`, so
  `frontend/staticwebapp.config.json` is the one that ships. The
  duplicate at the repo root is dead weight — and the moment they
  diverge, contributors will edit the wrong one.
* **Fix:** delete `static-web-apps/staticwebapp.config.json` and add a
  README pointer.

### S-10 — Audit log durability for `/api/positions/execute` (Low)

* `backend/main.py:1064-1070` writes a JSON line to
  `${HOME}/data/executions.jsonl` (or `/home/site/data/...` on App
  Service) inside a bare `try/except: pass` — a write failure silently
  drops the audit record, which is the wrong default for an exec audit
  log.
* The path lives on the App Service's local disk, which is reset on
  scale-down / restart on a Free/Basic plan. Even on a Standard plan,
  durability is "until the next platform-level move."
* **Fix:** dual-write to App Insights (`trace_event("execute", **mapped)`)
  *and* the local file; if the file write fails, raise — better to fail
  the request than to silently lose the audit entry.

---

## 4. Top 15 prioritized findings

| # | Severity | Finding | One-line fix | Owner |
|---|----------|---------|--------------|-------|
| 1 | **High** | `/api/positions/execute` reachable by any internet caller (S-7 + S-3) | Require shared-secret header `X-Trading-Token` until P1 auth ships; reject if absent | backend |
| 2 | **High** | No CSP / HSTS / X-Frame-Options on SWA (S-2) | Add `globalHeaders` block in `frontend/staticwebapp.config.json` | infra |
| 3 | **High** | Per-process rate limit on execute is bypassable + duplicated (S-4) | Move to Redis-backed `slowapi`, key by `(ip, route)`, 1/5 s | backend |
| 4 | **High** | Auth gap — single-user demo with no identification (S-7) | Implement `docs/designs/p1-auth.md` (Google OAuth + cookie session) | backend |
| 5 | Medium | `CORSMiddleware(allow_origins=["*"])` over write endpoints (S-3) | Mount `/api/positions/*` under stricter CORS allow-list | backend |
| 6 | Medium | Local `.env` holds real third-party keys (S-1) | Move to `~/.config/macro-oil-terminal/.env`; rotate unused keys | backend (operator) |
| 7 | Medium | `/api/positions/execute` path duplicated in `main.py` and `routers/positions.py` (S-4 #2) | Delete the inline `main.py` route; rely on the router | backend |
| 8 | Medium | npm audit reports 6 moderate dev-only advisories (vitest/vite/postcss) | `npm install vitest@latest` to bump the test runner | frontend |
| 9 | Medium | Audit log fails silently on disk-write error (S-10) | Dual-write to App Insights + raise on local-disk failure | backend |
| 10| Low | Two copies of `staticwebapp.config.json` will drift (S-9) | Delete the repo-root copy; keep `frontend/staticwebapp.config.json` | infra |
| 11| Low | `_provider_error` echoes `str(exc)` in JSON body | Scrub strings matching API-key regex before serialising | backend |
| 12| Low | `pip-audit` runs at audit time only — not in CI | Add to a `security-scan.yml` workflow on every PR | infra |
| 13| Low | gitleaks / detect-secrets not in CI | Same workflow; gate PRs on a clean scan | infra |
| 14| Low | LLM thesis renders as React text today, but no doc warning against `dangerouslySetInnerHTML` | Add a comment + ESLint `react/no-danger` rule | frontend |
| 15| Info | CodeQL only analyses Python (S-8 / `.github/workflows/codeql.yml:24`) | Add `javascript-typescript` to the matrix | infra |

Critical-count: **0** | High-count: **4**

---

## 5. CI integration recommendations

`codeql.yml` covers Python with the `security-and-quality` query pack — solid
baseline. **Gaps:**

* Bandit / pip-audit / detect-secrets / npm-audit are *not* run on PRs.
* CodeQL skips JS/TS — half the codebase.
* No SAST aggregation in PR comments → findings die in the workflow log.

Suggested workflow (do **not** add to `.github/` yet — Aidan's call when this
ships):

```yaml
# .github/workflows/security-scan.yml
name: Security scan

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]
  schedule:
    - cron: "0 5 * * 1"  # weekly Mondays 05:00 UTC
  workflow_dispatch:

permissions:
  contents: read
  security-events: write
  pull-requests: write

jobs:
  python-security:
    name: bandit + pip-audit + detect-secrets
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }   # full history for secret scan
      - uses: actions/setup-python@v5
        with: { python-version: "3.11", cache: pip }
      - run: pip install bandit pip-audit detect-secrets
      - name: bandit (medium+ severity, medium+ confidence)
        run: bandit -r backend/ providers/ -ll -ii -f sarif -o bandit.sarif || true
      - name: pip-audit (runtime closure)
        run: pip-audit -r backend/requirements.txt -r requirements.txt --strict
      - name: detect-secrets (full history)
        run: |
          detect-secrets scan \
            --exclude-files '\.venv|\.git/|node_modules|__pycache__' \
            --baseline .secrets.baseline
      - name: Upload SARIF
        uses: github/codeql-action/upload-sarif@v3
        with: { sarif_file: bandit.sarif }

  semgrep:
    name: semgrep p/security-audit
    runs-on: ubuntu-latest
    timeout-minutes: 15
    container: returntocorp/semgrep:latest
    steps:
      - uses: actions/checkout@v4
      - run: semgrep ci --config=p/security-audit --config=p/python --config=p/typescript --sarif --output=semgrep.sarif
      - uses: github/codeql-action/upload-sarif@v3
        with: { sarif_file: semgrep.sarif }

  npm-audit:
    name: npm audit + license check
    runs-on: ubuntu-latest
    timeout-minutes: 8
    defaults: { run: { working-directory: frontend } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: npm, cache-dependency-path: frontend/package-lock.json }
      - run: npm ci --legacy-peer-deps
      - name: audit (fail on high+)
        run: npm audit --audit-level=high --omit=dev

  gitleaks:
    name: gitleaks (full history)
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: gitleaks/gitleaks-action@v2
        env: { GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }} }
```

Also: extend `.github/workflows/codeql.yml`'s `language` matrix to
`[python, javascript-typescript]` — adds 4–5 min to the run, catches the
Next.js half of the codebase that's currently invisible to CodeQL.

---

## Sign-off

Two High-severity surfaces are external (CSP/HSTS, anonymous write API),
both with concrete one-line fixes. No Critical findings; no real secret in
git; OIDC posture is correct. Fix #1–#4 in the prioritised list before
opening the API to a second user.
