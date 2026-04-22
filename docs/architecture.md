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

    subgraph Compute[Streamlit / Python]
      DI[data_ingestion.py]
      QM[quantitative_models.py<br/>z-score · backtest · depletion]
      TC[thesis_context.py]
      TT[trade_thesis.py<br/>Azure OpenAI JSON schema]
      WG[webgpu_components.py<br/>Three.js TSL]
    end

    subgraph UI[Browser]
      T1[Tab 1<br/>Macro Arbitrage]
      T2[Tab 2<br/>Depletion Forecast]
      T3[Tab 3<br/>Fleet Analytics<br/>+ WebGPU globe]
      T4[Tab 4<br/>AI Trade Thesis]
    end

    AOAI[(Azure OpenAI<br/>gpt-4o-mini)]

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
    DI --> T1
    DI --> T2
    DI --> T3
    QM --> T1
    QM --> T2
    TT --> T4
    WG --> T3
    WG --> T1
```

## Deployment surface

```mermaid
flowchart LR
    GH[GitHub main] -->|push| CI[CI: test_runner.py]
    GH -->|push| CD[CD: OIDC → zip deploy]
    CD --> WA[Azure Web App F1<br/>oil-tracker-app-4281]
    WA --> CDN[three.js via jsdelivr<br/>Earth textures via threejs.org]
    WA <--> AOAI[Azure OpenAI<br/>oil-tracker-aoai]
    KW[GitHub Actions keep-warm<br/>*/5 07-22 UTC] --> WA
    User[End user browser] --> WA
```

## Security posture

* OIDC federated credentials for CD — **no Azure client secret in repo**.
* Azure OpenAI endpoint + key set as App Service App Settings, never in the source tree.
* Secret scanning via pre-commit `gitleaks` (opt-in local hook) and CodeQL (default Python queries, weekly cron + on every push).
* Dependabot watches pip + github-actions + docker, weekly PRs with `deps(*)` prefix.

## Notable trade-offs

* **F1 App Service** — 20s cold start, no always-on. Mitigated by a 5-min keep-warm ping during waking hours. Upgrade to B1 removes the quota block on always-on.
* **No real-time live AIS** without `AISSTREAM_API_KEY` — the UI surfaces a clearly labelled Q3 2024 historical fleet snapshot plus a one-click signup CTA. Key distribution is real; individual vessel names are placeholders.
* **yfinance 1-min intraday** has ~15-min publisher delay for futures — that's the free-tier ceiling. Twelve Data is wired as an upgrade behind `TWELVEDATA_API_KEY`.
* **WebGPU fallback** — Three.js `three/webgpu` with TSL material graphs, falling through to `three.module.js` + WebGL when `navigator.gpu` is unavailable. Earth textures served from `threejs.org/examples` (CC-licensed); if the texture CDN is unreachable we render the procedural navy fallback.
