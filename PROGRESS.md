# Autonomous build — progress log

Timestamps are UTC (sandbox time).

## 2026-04-21

### ~03:10 — Phase 1 kickoff
- Requested `~/Documents` cowork directory, created `~/Documents/macro_oil_terminal/`.
- Wrote `requirements.txt` with streamlit, pandas, numpy, plotly, scikit-learn, yfinance, requests.

### ~03:11 — Phase 2 (data_ingestion.py, 258 lines)
- `fetch_pricing_data(years=5)` via yfinance (BZ=F, CL=F) with deterministic synthetic fallback if network unreachable.
- `simulate_inventory(years=2)` — weekly index, 820 Mbbl start, ~160 Mbbl drawdown trend, 18 Mbbl seasonal wave, 4.5 Mbbl weekly noise.
- `generate_ais_mock(500)` — Panama/Liberia/US/Iran/Russia favored weights; added `Latitude`/`Longitude` scatter around flag hotspots so the 3D globe has real geography.

### ~03:12 — Phase 3 (quantitative_models.py, 221 lines)
- `compute_spread_zscore` — daily spread, 90d rolling Z with div-by-zero guard.
- `forecast_depletion` — sklearn LinearRegression on trailing N weeks; returns daily/weekly rates, projected floor-breach date, regression line DataFrame, R².
- `categorize_flag_states` — Jones Act / Domestic / Shadow Risk / Sanctioned / Other; always emits all four headline categories.

### ~03:14 — Phase 4 (app.py, 374 lines)
- Wide layout, 3 tabs, 3 sidebar sliders (Z threshold, floor Mbbl, depletion window).
- Tab 1: Plotly subplot — Scattergl Brent/WTI prices + Scattergl Z-score with horizontal red threshold lines at ±σ.
- Tab 2: Scattergl inventory + dashed regression projection + floor hline + breach vline, big st.metric values for rate + projected date.
- Tab 3: Plotly bar by category (green/amber/red/grey), 3D WebGPU globe below.
- No matplotlib anywhere. All line charts use `go.Scattergl`.

### ~03:15 — webgpu_components.py (464 lines)
- `render_hero_banner` — animated oil-slick fBm shader via `RawShaderMaterial` (works on WebGL + WebGPU backends), badge shows which is active.
- `render_fleet_globe` — InstancedMesh of 500 tanker dots on a sphere, lat/lon→3D, color-coded by category, drag to rotate, wheel to zoom.
- `navigator.gpu` gate → WebGPURenderer, else WebGLRenderer, else static fallback.

### ~03:16 — Phase 5 validation (test_runner.py, 266 lines)
- 20 checks across all modules. First run: **20/20 green**.
- yfinance blocked in sandbox → synthetic fallback kicks in → tests deterministic regardless.

### ~03:17 — Streamlit smoke test #1
- Port 8765, clean startup, "You can now view your Streamlit app in your browser", empty stderr.
- Follow-up test on port 8766: `/_stcore/health` → `ok`, `/` → HTTP 200.

### ~03:19 — README.md + DEPLOY.md + .gitignore
- Written. DEPLOY.md has full `gh` + `az` command blueprints for host execution.

### ~03:19–03:20 — Git attempt (mounted folder)
- Sandbox could `git init && git add -A` on the mounted `~/Documents/macro_oil_terminal/` but macOS sandbox perms prevented subsequent git operations from cleaning their own lock files. Left a half-init `.git/` at that path.
- Workaround: cloned files to `/tmp/macro_oil_terminal`, ran `git init/add/commit`, produced `macro-oil-terminal.bundle` in outputs.

### ~03:21 — Streamlit smoke test #2
- Clean startup confirmed with final code on port 8767.

### ~03:22 — Handover summary delivered
- Aidan asleep, test runner 20/20, smoke test passed, bundle + DEPLOY.md ready.

---

## Second autonomous block (host bridging)

### 12:21Z — Aidan confirms gh/az are installed + authed on host
- Pivoting sandbox-bash work to `osascript` so git/gh/az run as Aidan on macOS.
- git 2.50.1, gh 2.87.3, az 2.83.0 all on PATH (Homebrew).

### 12:22Z — Clean git init on host
- `rm -rf .git __pycache__ .venv` via osascript.
- `git init -b main && git add -A && git commit`. Author picked up from host config (Aidan2111 / 11aidanmarshall@live.com).

### 12:23Z — GitHub repo created + pushed
- `gh auth status` — active account Aidan2111, SSH + keyring token.
- `gh repo create macro-oil-terminal --public --source=. --remote=origin --push`
- URL: **https://github.com/Aidan2111/macro-oil-terminal**

### 12:24Z — Azure tenant verified
- `az account show` → tenant Youbiquity, subscription `5ae389ef-a76f-4564-95e8-dc2b28ed0f40`.

### 12:25Z — RG + App Service plan
- `az group create --name oil-price-tracker --location eastus` → success.
- B1 plan in eastus → quota 0 error. F1 in eastus → quota 0 error.
- Swept regions: F1 succeeded in westus2, centralus, westus3, westeurope, canadacentral, francecentral.
- Kept `oil-tracker-plan-westus2`, deleted the other 5.

### 12:27Z — Web App + startup config
- `az webapp create --name oil-tracker-app-4281 --runtime PYTHON:3.11`.
- `az webapp config set` with Streamlit startup: `python -m streamlit run app.py --server.port 8000 --server.address 0.0.0.0 --server.headless true --browser.gatherUsageStats false` + `--web-sockets-enabled true`.
- App settings: `SCM_DO_BUILD_DURING_DEPLOYMENT=true`, `ENABLE_ORYX_BUILD=true`, `WEBSITES_PORT=8000`.
- `--always-on true` → Conflict on F1 (expected).

### 12:28Z — Azure OpenAI
- `az cognitiveservices account create --kind OpenAI --sku S0 --location eastus --yes` → success.
- `az cognitiveservices account update --custom-domain oil-tracker-aoai` → endpoint now `https://oil-tracker-aoai.openai.azure.com/`.
- `gpt-4o-mini` deployment created (model version 2024-07-18, GlobalStandard SKU, capacity 10).
- Endpoint + key stored as App Service app settings (AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_KEY / AZURE_OPENAI_API_VERSION / AZURE_OPENAI_DEPLOYMENT). **Key never written to repo.**

### 12:30Z — Feature: AI Insights tab
- `ai_insights.py` with `InsightContext` dataclass and `generate_commentary` helper.
- 4th Streamlit tab wires the snapshot into the prompt; graceful `_canned_commentary` fallback when env vars are missing.
- `openai`, `python-dotenv` added to requirements.txt; `.env.example` seeded.
- test_runner grew to 24 checks (canned, snapshot, no-env fallback).
- Smoke test green on port 8768.
- Commit `d4cf0aa` pushed to main.

### 12:34Z — Feature: TSL hero + textured Earth globe
- three.js pin bumped from 0.160 → 0.170 (stable `three/webgpu` + `three/tsl` ES entries).
- Hero: `MeshBasicNodeMaterial` + `Fn()` colorNode using `mx_fractal_noise_float` + `oscSine(time)` for scan lines. WebGL path keeps equivalent classic GLSL RawShaderMaterial.
- Globe: TSL day/night material via `dot(normal, sunDir)` lambert gate + `texture()` sampling of `earth_atmos_2048.jpg` + `earth_lights_2048.png`, auto-rotating sun, rim light. WebGL path uses MeshPhongMaterial with emissiveMap; navy procedural fallback if textures are unreachable. Atmosphere scattering shell on both backends.
- `renderer.setAnimationLoop` + `renderAsync` for WebGPU.
- Commit `2c8398c` pushed.

### 12:38Z — Feature: backtest, CSV exports, dark theme, Dockerfile
- `backtest_zscore_meanreversion`: enter at ±threshold, exit when |Z|<0.2, 10 kbbl notional. Per-trade blotter + cumulative equity curve.
- Tab 1 rendering: stats row + Scattergl equity curve + expander with blotter and CSV download. Tab 2: CSV for inventory + projection. Tab 3: CSV for fleet roster.
- `data_ingestion.fetch_live_ais`: documented aisstream.io stub (key-gated per upstream policy).
- Streamlit dark theme (oil-black + amber accent) via `.streamlit/config.toml`. All Plotly figures migrated to `plotly_dark`.
- `Dockerfile` + `.dockerignore` for portable deploy.
- Test runner now 27/27 green.
- Commit `c88b641` pushed.

### 12:41Z — Screenshots via Playwright
- Installed `.venv` + requirements on host.
- `playwright install chromium`; `capture_screens.py` iterates the 4 tabs with `get_by_role("tab")` + 2.5s render wait.
- 5 PNGs in `docs/screenshots/`; README now embeds them.

### 12:43Z — Live Azure OpenAI smoke test
- Exported endpoint + key from the resource, ran `ai_insights.generate_commentary` with a realistic context. Model returned coherent Commentary + 3 risk bullets, ended with "Live — Azure OpenAI gpt-4o-mini".

### 12:45Z — GitHub Actions CI
- `.github/workflows/ci.yml`: matrix Python 3.11/3.12, runs `test_runner.py`, plus a Streamlit boot+healthz smoke job.

### 12:50Z — Zip deploy to Azure Web App
- First deploy: Kudu returned 400 "Deployment Failed" even though build phase was clean (0 errors/warnings). The site served Streamlit HTML anyway (HTTP 200).
- Runtime crashed inside simulate_inventory: pandas 2.x returned 103 rows from `pd.date_range(end=today, periods=104, freq="W-FRI")` when `end` didn't align to the Friday anchor; DataFrame construction then mismatched a 104-length `values` array.

### 12:53Z — Hotfix + redeploy
- Built `idx` first and sized `trend`, `seasonal`, `noise`, `values` from `len(idx)`; added `W-FRI → 7D` fallback when the range returns empty.
- Regression test `simulate_inventory(length_consistency)` covering years ∈ {1, 2, 3, 5}. test_runner now 28/28 green.
- Zip deploy #2: `RuntimeSuccessful`. Live screenshot confirmed — Brent $95.48 / WTI $89.61, backtest 11 trades / $252,900 PnL / 100% win rate.
- **Live URL:** https://oil-tracker-app-4281.azurewebsites.net


