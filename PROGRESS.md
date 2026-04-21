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

### ~03:30 — Aidan confirms gh/az are installed + authed on host
- Pivoting sandbox-bash work to `osascript` so git/gh/az run as Aidan on macOS.

