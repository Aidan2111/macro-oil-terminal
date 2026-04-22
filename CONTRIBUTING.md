# Contributing

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
