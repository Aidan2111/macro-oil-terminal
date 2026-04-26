# Security

## Reporting

Open a GitHub Security Advisory on `Aidan2111/macro-oil-terminal` or email
the repo owner directly. Please do not open a public issue for vulnerability
disclosures.

## Secret handling

All secrets live as environment variables or cloud App Settings.
**No secret is ever committed to the repo.**

* `AZURE_OPENAI_*` — set as Azure App Service App Settings.
* `AISSTREAM_API_KEY` — optional, local `.env` or App Setting.
* `ALPACA_API_KEY_ID` / `ALPACA_API_SECRET` — App Service settings only;
  paper-trading scope is hard-pinned in `backend/services/alpaca_service.py`.
* `EIA_API_KEY`, `FRED_API_KEY`, `TWELVEDATA_API_KEY`, `DATABENTO_API_KEY`,
  `ALERT_SMTP_*` — optional.
* Azure CD uses **OIDC federated credentials** — no long-lived Azure client secret.

`.gitignore` excludes `.env`, `.env.*` (except `.env.example`), `data/`, and
CLI-written session files under `.agent-scripts/`.

### `.env` discipline (review #14, finding S-1)

* `.env` is `.gitignore`d at the repo root and has **never been tracked**
  (verified via `git log --all --full-history -- .env`).
* Real third-party API keys live ONLY in:
  - Azure App Service App Settings (production)
  - the contributor's local `~/.config/macro-oil-terminal/.env` (preferred
    location; outside the repo working directory) or a repo-root `.env`
    that is gitignored
* **Never echo secrets in logs.** The keys we care about specifically are:
  - `ALPACA_API_SECRET`
  - `AISSTREAM_API_KEY`
  - `AZURE_OPENAI_API_KEY`
  - `EIA_API_KEY`, `FRED_API_KEY`, `DATABENTO_API_KEY`
  `_provider_error()` in `backend/main.py` interpolates `str(exc)` into the
  503 response body — verified safe today (yfinance / openai-py do not
  embed credentials in their error messages at the pinned versions), but
  re-verify whenever a provider library is upgraded.
* `backend/services/alpaca_service.py` is the canonical example of safe
  mapping: every Alpaca SDK object passes through a whitelist projector
  (`map_position`, `map_account`, `map_order`) before reaching the wire,
  so the secret cannot leak via accidental serialisation.

Pre-commit `gitleaks` (opt-in via `.pre-commit-config.yaml`) catches
accidental commits. GitHub secret scanning + CodeQL
(`.github/workflows/codeql.yml`) run on every push and weekly on a cron.

### Weekly CI security smoke (review #14, section 5)

`.github/workflows/security-scan.yml` runs on every PR + push to main +
weekly cron (Mondays 05:00 UTC) + `workflow_dispatch`:

* `bandit -r backend/ providers/ -ll -ii` — medium+ severity, medium+
  confidence. Audit-time baseline (2026-04-25): **0 findings**.
* `pip-audit -r backend/requirements.txt -r requirements.txt --strict` —
  strict mode treats any advisory as a failure. Baseline: **0 vulns**.
* `cd frontend && npm audit --audit-level=high` — high+ only.
  Baseline: **0 high/critical**. There are 6 known moderate dev-only
  advisories (vitest/vite/postcss) — tracked in review #14 §2.3, not
  in the production runtime closure, do not block this gate.

Any new finding above those baselines fails the job.

## Browser security headers (CSP, HSTS, X-Frame-Options)

`frontend/staticwebapp.config.json` is the authoritative SWA config and
sets the following `globalHeaders` on every response:

* `Content-Security-Policy` —
  `default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' https://oil-tracker-api-canadaeast-0f18.azurewebsites.net wss://stream.aisstream.io; frame-ancestors 'none'; base-uri 'self'`
  (`'unsafe-inline'` for scripts/styles is required by Next 15's CSS-in-JS
  until a nonce middleware ships; revisit when phase-2 auth lands.)
* `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload`
* `X-Frame-Options: DENY`  (belt-and-braces with `frame-ancestors 'none'`)
* `X-Content-Type-Options: nosniff`
* `Referrer-Policy: strict-origin-when-cross-origin`
* `Permissions-Policy: camera=(), microphone=(), geolocation=()`

The previous duplicate `static-web-apps/staticwebapp.config.json` was
collapsed in Wave 4 (review #14, S-9) to prevent drift. Edit only
`frontend/staticwebapp.config.json`.

## Trade-execution endpoint posture

`POST /api/positions/execute` is the only write endpoint. Wave 4 adds
two layers in front of it:

* **Origin allowlist (review #14, S-3)** — `backend/security.require_execute_origin`
  rejects any browser POST whose `Origin` is not the production SWA
  (`https://delightful-pebble-00d8eb30f.7.azurestaticapps.net`) or
  `localhost:3000` / `127.0.0.1:3000`. Empty/absent Origin (curl,
  Postman, server-to-server) bypasses the gate — this is defence-in-depth
  against drive-by browser POSTs, not authn/z. Real auth is phase-2.
* **Persistent rate limit (review #14, S-4)** —
  `backend/security.enforce_execute_rate_limit` is a file-backed dual
  gate at `data/rate-limit-execute.json`:
  - Inner floor: 1 request per 2s.
  - Outer ceiling: 30 requests per 5-minute trailing window.
  Both gates 429 with a `Retry-After` header. State path is overridable
  via `RATE_LIMIT_STATE_DIR` (used by tests).

## Streamlit (legacy) — known limitation

The legacy Streamlit app at `oil-tracker-app-canadaeast-4474` cannot be
fronted with the same CSP/HSTS headers because Streamlit serves `/`
itself. App Service terminates TLS and denies iframe embedding by
default via its edge settings; that's the posture Streamlit gets.
The Next.js stack (this PR's target) is the place where CSP/HSTS now
live.
