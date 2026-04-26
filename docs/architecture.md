# Architecture

## Data flow

```mermaid
flowchart LR
    subgraph Sources[Real sources — no simulators]
      YF[Yahoo Finance<br/>BZ=F / CL=F<br/>daily + 1-min intraday]
      EIA[EIA dnav<br/>LeafHandler.ashx<br/>WCESTUS1 + WCSSTUS1]
      FRED[FRED API<br/>observations<br/>fallback, keyed]
      AIS[aisstream.io<br/>websocket<br/>keyed, optional]
    end

    subgraph Providers[providers/ package]
      PP[pricing.py]
      PI[inventory.py]
      PA[ais.py]
    end

    subgraph Compute[Python — shared modules]
      DI[data_ingestion.py]
      QM[quantitative_models.py<br/>z-score · backtest · depletion]
      TC[thesis_context.py]
      TT[trade_thesis.py<br/>Azure OpenAI / Foundry JSON schema]
    end

    subgraph Backend[FastAPI backend/]
      MAIN[backend.main:app]
      SVC[backend/services/*<br/>spread · thesis · positions · cftc · inventory · fleet · backtest]
    end

    subgraph UI[Browser — Next.js 15 SWA]
      F1[Macro Arbitrage<br/>Spread Stretch]
      F2[Inventory drawdown]
      F3[Tanker fleet<br/>+ WebGPU globe]
      F4[Hero band<br/>AI Trade Thesis]
    end

    AOAI[(Azure OpenAI<br/>gpt-4o-mini / o4-mini)]
    FOUNDRY[(Azure AI Foundry<br/>agent service)]

    YF --> PP
    EIA --> PI
    FRED --> PI
    AIS --> PA
    PP --> DI
    PI --> DI
    PA --> DI
    DI --> QM
    DI --> TC
    QM --> TC
    TC --> TT
    TT <--> AOAI
    TT <--> FOUNDRY
    DI --> SVC
    QM --> SVC
    TT --> SVC
    SVC --> MAIN
    MAIN --> F1
    MAIN --> F2
    MAIN --> F3
    MAIN --> F4
```

## Deployment surface

```mermaid
flowchart LR
    GH[GitHub main] -->|push touches backend/ or frontend/| CD[CD: cd-nextjs.yml<br/>OIDC -> backend zip + SWA upload]
    GH -->|push| CI[CI: ci.yml + ci-nextjs.yml<br/>pytest + npm lint/test/build]
    CD --> API[Azure App Service<br/>oil-tracker-api-canadaeast-0f18]
    CD --> SWA[Azure Static Web App<br/>delightful-pebble-00d8eb30f.7.azurestaticapps.net]
    SWA -->|fetch JSON over CORS| API
    SWA --> CDN[three.js via jsdelivr<br/>Earth textures via threejs.org]
    API <--> AOAI[Azure OpenAI<br/>oil-tracker-aoai]
    API <--> FOUNDRY[Azure AI Foundry<br/>agent service]
    KW[GitHub Actions keep-warm<br/>*/10 07-22 UTC] --> API
    KW --> SWA
    User[End user browser] --> SWA
```

> The legacy Streamlit web app at `oil-tracker-app-canadaeast-4474` was
> retired on 2026-04-26 (code-side teardown) and decommissioned via
> `scripts/streamlit-decommission.sh` once the 2026-04-27 04:00 UTC
> stable window opened.

## Security posture

* OIDC federated credentials for CD — **no Azure client secret in repo**.
* Azure OpenAI / Foundry endpoint + key set as App Service App Settings, never in the source tree.
* Secret scanning via pre-commit `gitleaks` (opt-in local hook) and CodeQL (default Python queries, weekly cron + on every push).
* Dependabot watches pip + github-actions + docker, weekly PRs with `deps(*)` prefix.

## Notable trade-offs

* **Azure App Service B1** — cold-start dominated; warmed by `keep-warm.yml` every 10 min during waking hours.
* **No real-time live AIS** without `AISSTREAM_API_KEY` — the UI surfaces a clearly labelled Q3 2024 historical fleet snapshot plus a one-click signup CTA. Key distribution is real; individual vessel names are placeholders.
* **yfinance 1-min intraday** has ~15-min publisher delay for futures — that's the free-tier ceiling. Twelve Data is wired as an upgrade behind `TWELVEDATA_API_KEY`.
* **WebGPU fallback** — Three.js `three/webgpu` with TSL material graphs, falling through to `three.module.js` + WebGL when `navigator.gpu` is unavailable. Earth textures served from `threejs.org/examples` (CC-licensed); if the texture CDN is unreachable we render the procedural navy fallback.
