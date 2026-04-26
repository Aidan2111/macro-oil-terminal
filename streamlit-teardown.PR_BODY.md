## Streamlit teardown — code-side cleanup (Azure delete deferred)

The React/FastAPI stack hit 48h of clean uptime; this PR lands the
code-side half of the Streamlit teardown. The Azure web app + plan
delete is deferred to `scripts/streamlit-decommission.sh`, which runs
manually after the **2026-04-27 04:00 UTC** decommission window opens.

### What's removed now

- `app.py` (Streamlit entry point)
- `Dockerfile` + `.dockerignore` (Streamlit-only image)
- `.streamlit/` (Streamlit runtime config + secrets example)
- `tests/e2e/` — every test booted a headless Streamlit via the
  `streamlit_server` fixture
- `tests/unit/test_input_hardening.py` — pulled `_clamp` out of
  `app.py` via regex; obsolete with `app.py` gone
- `test_runner.py` — legacy Streamlit "27-check" validator
- `.github/workflows/cd.yml` (Streamlit CD pipeline)
- `.github/workflows/e2e.yml` (Playwright pipeline targeting Streamlit)
- `streamlit` + `plotly` from `requirements.txt`
- The Streamlit canadaeast `/_stcore/health` ping in `keep-warm.yml`
- `streamlit-smoke` + `legacy-runner` jobs in `ci.yml`
- One test in `test_ux_revision_v2.py` that read `app.py`; the
  remaining theme-CSS regression tests in that file stay
- README / CONTRIBUTING / docs/architecture.md rewritten around
  Next.js + FastAPI; Streamlit retirement noted in PROGRESS.md

### What's deferred

- Azure web app delete: `oil-tracker-app-canadaeast-4474`
- App Service plan delete: `oil-tracker-canadaeast-plan` (only if
  `numberOfSites == 0` after the web app is gone)

Both happen via:

```
./scripts/streamlit-decommission.sh --i-have-confirmed-window-passed
```

The script pre-flights the React SWA + FastAPI `/health`; aborts if
either is down. Refuses to run without the explicit flag.

### Flagged ambiguous, left in place

Per the "if it's ambiguous, leave it and flag" rule:

- **`static/logo.svg` + `static/favicon.ico`** — referenced by `theme.py`
  and `tests/unit/test_theme_meta.py`. Removing the assets would break
  those tests; removing `theme.py` is out of scope ("only the Streamlit
  entry surface"). The React app has its own `frontend/app/favicon.ico`,
  so these aren't shared.
- **`theme.py`, `auth/`, `webgpu_components.py`** — only imported by the
  retired `app.py` today, but the React stack may want to crib bits.
  Leaving in place; backend doesn't import them via the
  `backend.services._compat` shim.
- **`.github/workflows/release.yml`** — still targets the decommissioned
  `oil-tracker-app-4281` (westus2) Streamlit web app and runs
  `test_runner.py`. It's already broken (target gone; script gone). Re-pointing
  it at a tag-driven SWA release is a follow-up cleanup PR.
- **`.env.example` Streamlit env vars** (`STREAMLIT_COOKIE_SECRET`,
  `STREAMLIT_ENV`, `MOCK_AUTH_USER`) — still consumed by `auth/` modules
  that are kept.

### Validation

- `pytest tests/unit/` → 304 passed, 2 skipped (network/live-LLM)
- `pytest backend/tests/` → 21 pre-existing failures on `main` (unrelated
  to this PR; documented in PROGRESS.md as "Fixture-backed mode: legacy
  tests target the old service-layer API and no longer match"). Smoke-import
  of `backend.main` still passes — the gate `cd-nextjs.yml` enforces.
- `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml').read())"` clean
- `bash -n scripts/streamlit-decommission.sh` clean; guard refuses
  to run without the flag.
- Frontend (`npm run lint && npm run typecheck && npm test`) **not run
  in the agent sandbox** — no `node` / `npm` toolchain available. Worth
  re-running locally before merge.

### Operator runbook

After merge:

```bash
# Wait until 2026-04-27 04:00 UTC.
git pull origin main
./scripts/streamlit-decommission.sh --i-have-confirmed-window-passed
```
