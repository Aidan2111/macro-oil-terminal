# Contributing

## Development workflow

Any change bigger than a typo fix goes through: **brainstorm → design →
worktree → plan → TDD → review → finish**. See [`docs/workflow.md`](docs/workflow.md)
for the full picture, and `docs/brainstorms/`, `docs/designs/`, `docs/plans/`
for in-flight work.

TL;DR:

1. Write a brainstorm in `docs/brainstorms/<feature>.md` (problem + alternatives).
2. Distil a spec in `docs/designs/<feature>.md` (reviewable in 5 minutes).
3. Break into tasks in `docs/plans/<feature>.md` (2–5 min each, tests-first).
4. `git worktree add ../macro_oil_terminal-<feature> <feature>` — work happens there.
5. Red → Green → Refactor → Commit, per task.
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
pip install -r requirements.txt

# (optional) enable opt-in pre-commit hooks: gitleaks, ruff, trailing-ws, …
pip install pre-commit && pre-commit install

cp .env.example .env   # fill in AZURE_OPENAI_* if you want the Trade Thesis tab to call the real model
python test_runner.py  # must be 24/24 green before you push
streamlit run app.py
```

## Test gate

`test_runner.py` is the authoritative check. CI runs it on every push to `main`
and on every pull request. Add a new check under the appropriate `test_*`
section whenever you touch a module.

## CD expectations

Every push to `main` triggers `.github/workflows/cd.yml`:

1. `pip install -r requirements.txt`
2. `python test_runner.py` (blocks the deploy if any check fails)
3. `azure/login@v2` via OIDC federated credential — no client secret.
4. Zip → `azure/webapps-deploy@v3` → `oil-tracker-app-4281`.
5. Post-deploy `/_stcore/health` retry loop (10 attempts, 10s gaps).

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
app.py                  # Streamlit entrypoint (tabs, sidebar, WebGPU hooks)
data_ingestion.py       # Public API over providers/
providers/              # Real-data adapters: EIA, FRED, yfinance, aisstream
quantitative_models.py  # Spread z-score, depletion, categorisation, backtest
webgpu_components.py    # Three.js TSL hero + day/night Earth globe
trade_thesis.py         # Azure OpenAI JSON-schema thesis generator
thesis_context.py       # Rich real-data payload builder
alerts.py               # SMTP email alert stub
test_runner.py          # 24-check validation suite
```

## Questions

Open a draft PR or an issue. Keep CI green; keep the live site up.
