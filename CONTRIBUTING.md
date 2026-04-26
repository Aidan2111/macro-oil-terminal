# Contributing

## Development workflow

Any change bigger than a typo fix goes through: **brainstorm -> design ->
worktree -> plan -> TDD -> review -> finish**. See [`docs/workflow.md`](docs/workflow.md)
for the full picture, and `docs/brainstorms/`, `docs/designs/`, `docs/plans/`
for in-flight work.

TL;DR:

1. Write a brainstorm in `docs/brainstorms/<feature>.md` (problem + alternatives).
2. Distil a spec in `docs/designs/<feature>.md` (reviewable in 5 minutes).
3. Break into tasks in `docs/plans/<feature>.md` (2–5 min each, tests-first).
4. `git worktree add ../macro_oil_terminal-<feature> <feature>` — work happens there.
5. Red -> Green -> Refactor -> Commit, per task.
6. Review after each task. Critical issues block progress.
7. `finishing-a-development-branch`: verify tests, merge to main, clean up worktree.

This workflow is Superpowers-inspired; if you're using Claude Code, install
the plugin (`/plugin install superpowers@claude-plugins-official`) and the
skills trigger automatically. If you're working by hand, `docs/workflow.md`
describes the whole thing in plain terms.

**Skip the workflow only for:** typo fixes, Dependabot bumps, docs-only changes,
log message tweaks.

## Quick start

```bash
git clone git@github.com:Aidan2111/macro-oil-terminal.git
cd macro-oil-terminal
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r backend/requirements.txt

# (optional) enable opt-in pre-commit hooks: gitleaks, ruff, trailing-ws, ...
pip install pre-commit && pre-commit install

cp .env.example .env   # fill in AZURE_OPENAI_* (or USE_FOUNDRY=true + Foundry vars)

# Run the unit suite (fast, offline)
python -m pytest tests/unit backend/

# Boot the FastAPI backend on :8000
uvicorn backend.main:app --reload --port 8000

# In another shell, boot the Next.js dev server on :3000
cd frontend && npm ci --legacy-peer-deps
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run dev
```

## Test gate

`pytest` under `tests/unit/` and `backend/tests/` is the authoritative check.
CI runs both on every push to `main` and on every pull request.

The frontend gate is `npm run lint && npm run typecheck && npm test` from the
`frontend/` directory; CI runs the same trio in `ci-nextjs.yml`.

## CD expectations

Every push to `main` that touches `backend/**` or `frontend/**` triggers
`.github/workflows/cd-nextjs.yml`:

1. `pip install -r requirements.txt -r backend/requirements.txt`
2. Smoke-import `backend.main` (full pytest gate returns once services re-wire)
3. `azure/login@v3` via OIDC federated credential — no client secret.
4. Zip `backend/` + shared root modules -> `azure/webapps-deploy@v3` ->
   `oil-tracker-api-canadaeast-0f18`.
5. `next build` (with `NEXT_PUBLIC_API_URL` baked in) -> `Azure/static-web-apps-deploy@v1`
   -> `delightful-pebble-00d8eb30f.7.azurestaticapps.net`.
6. Post-deploy `/api/build-info` SHA-match retry loop (15 attempts, 15s gaps).

If your change alters the data contract (e.g. adds a required env var),
update both `.env.example` and `DEPLOY.md` in the same commit.

## Data policy

* **No simulated data in production paths.** The `providers/` package handles
  real feeds; on total failure the UI raises a clear error state with a retry
  button — never silently substitutes fake numbers.
* Keys live in env vars only. Never commit secrets. `gitleaks` is wired via
  pre-commit to catch accidents; CodeQL runs on every push.

## Commit style

* `feat:` / `fix:` / `docs:` / `ci:` / `perf:` / `refactor:` / `test:` prefixes.
* Imperative subject, hard-wrap body at ~72 chars.
* Reference the related Task ID if relevant (see `PROGRESS.md`).

## Code layout

```
frontend/               # Next.js 15 App Router UI (hero band, charts, fleet globe)
backend/                # FastAPI service (router stubs + Pydantic schemas)
data_ingestion.py       # Public API over providers/
providers/              # Real-data adapters: EIA, FRED, yfinance, aisstream
quantitative_models.py  # Spread z-score, depletion, categorisation, backtest
trade_thesis.py         # Azure OpenAI / Foundry JSON-schema thesis generator
thesis_context.py       # Rich real-data payload builder
alerts.py               # SMTP email alert stub
scripts/                # Operational scripts (Streamlit decom, etc.)
```

## Questions

Open a draft PR or an issue. Keep CI green; keep the live site up.
