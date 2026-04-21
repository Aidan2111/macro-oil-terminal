# Inventory-Adjusted Spread Arbitrage & AIS Fleet Analytics Model

A Streamlit terminal for an oil desk: Brent/WTI dislocation z-scores, US
inventory drawdown velocity, and mock AIS-based tanker fleet exposure by
regulatory regime, with a WebGPU/Three.js TSL hero shader, a textured
day/night Earth globe, and an Azure OpenAI-backed market-commentary panel.

## Screens

![Macro Arbitrage](docs/screenshots/01_macro_arbitrage.png)
![Depletion Forecast](docs/screenshots/02_depletion_forecast.png)
![Fleet Analytics](docs/screenshots/03_fleet_analytics.png)
![AI Insights](docs/screenshots/04_ai_insights.png)

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Structure

| File | Purpose |
| --- | --- |
| `app.py` | Streamlit UI — 4 tabs, sidebar sliders, Plotly + WebGPU visuals |
| `data_ingestion.py` | yfinance pricing (5y), simulated 2y inventory, 500-vessel AIS mock, aisstream.io stub |
| `quantitative_models.py` | Brent-WTI spread Z-score, depletion regression, flag-state categorization, mean-reversion backtest |
| `webgpu_components.py` | Three.js TSL hero shader + day/night Earth globe (WebGL fallback) |
| `ai_insights.py` | Azure OpenAI commentary with deterministic canned fallback |
| `test_runner.py` | Autonomous validation — 27 checks across all modules |
| `Dockerfile` | Linux + Python 3.11 image, Streamlit entrypoint on :8000 |
| `DEPLOY.md` | GitHub + Azure command blueprints |

## Sidebar controls

- **Z-Score Alert Threshold** (default 3.0σ)
- **Inventory Floor** (default 300 Mbbl)
- **Depletion Rolling Window** (default 4 weeks)

## Tabs

1. **Macro Arbitrage** — Brent vs WTI prices + 90-day rolling Z-score of the
   spread. Horizontal red lines mark the user threshold. Historical
   mean-reversion backtest below (equity curve + trade blotter + CSV).
   All line charts use `plotly.graph_objects.Scattergl` (WebGL).
2. **Depletion Forecast** — Total US inventory (commercial + SPR) with a
   dashed linear-regression projection. Big-metric values for daily
   drawdown rate and projected floor breach date.
3. **Fleet Analytics** — Aggregate Mbbl on water by three categories
   (Jones Act / Domestic, Shadow Risk, Sanctioned), plus an interactive
   Three.js WebGPU Earth globe (day/night via TSL) with instanced tanker
   points colored by category.
4. **AI Insights** — Azure OpenAI-generated commentary synthesising the
   current Z-score, depletion rate, and fleet mix into a short trader
   note plus three risk bullets. Falls back to a deterministic canned
   narrative if `AZURE_OPENAI_ENDPOINT`/`AZURE_OPENAI_KEY` aren't set.

## Validation

```bash
python test_runner.py
```

Covers every public function in `data_ingestion.py` and
`quantitative_models.py`, plus payload-shape tests on the WebGPU helpers.
The yfinance call degrades to a synthetic fallback if the network is
unreachable, so tests remain deterministic offline.

## Notes

- Pricing source: yfinance tickers `BZ=F` (Brent) and `CL=F` (WTI). If
  the network is unreachable, a deterministic synthetic series stands in.
- Inventory is simulated (no EIA/FRED key) with realistic long-run
  drawdown + weekly noise + seasonal wave.
- AIS is entirely mocked (500 rows) — weighted toward Panama, Liberia,
  US, Iran, Russia flags with plausible lat/lon scatter around shipping
  lane hotspots.
- The WebGPU globe requires a browser that exposes `navigator.gpu`
  (Chrome 113+ / Edge 113+). It falls back to WebGL automatically.
- **Not investment advice.**

## Deployment

See `DEPLOY.md` for GitHub + Azure command blueprints.
