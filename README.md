# Inventory-Adjusted Spread Arbitrage & AIS Fleet Analytics Model

A Streamlit terminal for an oil desk: Brent/WTI dislocation z-scores, US
inventory drawdown velocity, and mock AIS-based tanker fleet exposure by
regulatory regime, with an optional WebGPU/Three.js TSL 3D globe.

## Quick start

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Structure

| File | Purpose |
| --- | --- |
| `app.py` | Streamlit UI — 3 tabs, sidebar sliders, Plotly + WebGPU visuals |
| `data_ingestion.py` | yfinance pricing (5y), simulated 2y inventory, 500-vessel AIS mock |
| `quantitative_models.py` | Brent-WTI spread Z-score, depletion regression, flag-state categorization |
| `webgpu_components.py` | Three.js/WebGPU hero banner + 3D fleet globe (fall back to WebGL) |
| `test_runner.py` | Autonomous validation — 20 checks across all modules |

## Sidebar controls

- **Z-Score Alert Threshold** (default 3.0σ)
- **Inventory Floor** (default 300 Mbbl)
- **Depletion Rolling Window** (default 4 weeks)

## Tabs

1. **Macro Arbitrage** — Brent vs WTI prices + 90-day rolling Z-score of the
   spread. Horizontal red lines mark the user threshold. All line charts use
   `plotly.graph_objects.Scattergl` (WebGL).
2. **Depletion Forecast** — Total US inventory (commercial + SPR) with a
   dashed linear-regression projection. Big-metric values for daily
   drawdown rate and projected floor breach date.
3. **Fleet Analytics** — Aggregate Mbbl on water by three categories
   (Jones Act / Domestic, Shadow Risk, Sanctioned), plus an interactive
   Three.js WebGPU globe with instanced tanker points colored by category.

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
