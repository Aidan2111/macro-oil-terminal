# Next.js + FastAPI stack migration — Design spec

> **Status:** DRAFT (2026-04-23). Review target: 5 minutes. Skim the
> module surface + the route map + the deploy topology + the 10-phase
> outline, and you know how the plan tasks hang together. Every
> decision cites the brainstorm (`docs/brainstorms/nextjs-fastapi-migration.md`)
> or the source brief (Aidan's spec sheet, 2026-04-23) by section.

## One-paragraph summary

A new `backend/` directory ships a FastAPI app factory with per-route
modules (health, build-info, spread, thesis, positions, CFTC, inventory,
fleet). A new `frontend/` directory ships a Next.js 15 App Router
scaffold with shadcn-ready tokens, a sticky left / bottom-tab Nav, a
Footer that reads from `/api/build-info`, and loading / empty / error
primitives. A new `.github/workflows/cd-nextjs.yml` deploys both
halves to Azure (App Service + Static Web Apps) with test gates and
live-verify steps mirroring the existing Streamlit pipeline. The
Streamlit app is untouched; its CD keeps shipping. Phases 1–10 in the
plan mirror the brief: Scaffold → Backend endpoints → Frontend
foundation → Hero card → Ticker tape → Chart pages → Globe →
Positions + track record → Cutover → Streamlit teardown.

## Module surface

```
backend/
  __init__.py
  main.py                      # FastAPI app factory + CORS + /health
  routers/
    __init__.py
    build_info.py              # GET /api/build-info
    health.py                  # GET /health, /api/health
    spread.py                  # GET /api/spread (stub P1; real in P2)
    thesis.py                  # GET /api/thesis/latest + POST SSE
    positions.py               # stub
    cftc.py                    # stub
    inventory.py               # stub
    fleet.py                   # stub
  services/                    # thin adapters over existing modules
    __init__.py
    spread_service.py
    thesis_service.py
  models/                      # pydantic v2 schemas
    __init__.py
    build_info.py
    thesis.py
    spread.py
  tests/
    __init__.py
    test_health.py             # GET /health → {"ok": True}
    test_build_info.py         # GET /api/build-info → sha/time/region
  requirements.txt
  pyproject.toml

frontend/
  app/
    layout.tsx                 # <html>, Inter font, Providers
    page.tsx                   # hero placeholder + ticker placeholder
    globals.css                # Tailwind directives + tokens import
    favicon.ico
  components/
    common/
      Nav.tsx                  # sticky left desktop / bottom-tab mobile
      Footer.tsx               # build-info + disclaimer
      LoadingSkeleton.tsx
      EmptyState.tsx
      ErrorState.tsx
  lib/
    api.ts                     # fetch wrapper + React Query client
    sse.ts                     # EventSource helper
  styles/
    tokens.css                 # palette tokens (CSS custom properties)
  public/
  tailwind.config.ts
  postcss.config.mjs
  next.config.mjs
  tsconfig.json
  package.json
  .eslintrc.json
  .gitignore

static-web-apps/
  staticwebapp.config.json     # /api/* → FastAPI proxy

.github/workflows/
  cd-nextjs.yml                # new, parallel to cd.yml
```

References brief sections: "Repo scaffold" (§2), "Module surface"
(§3.1). The Streamlit files (`app.py`, `theme.py`, `language.py`,
providers, data_ingestion.py, quantitative_models.py, etc.) are
**not** modified by this branch.

## Route map

| Method | Backend route | Frontend route | Phase |
|---|---|---|---|
| GET | `/health` | — | 1 |
| GET | `/api/health` | — | 1 |
| GET | `/api/build-info` | `/build-info.txt` (static asset) | 1 |
| GET | `/api/spread` | `/` (hero consumes) | 2 |
| GET | `/api/thesis/latest` | `/` (hero consumes) | 2 |
| POST | `/api/thesis/generate` (SSE) | `/` (hero streams) | 4 |
| GET | `/api/positions` | `/positions` | 8 |
| GET | `/api/cftc` | `/macro` | 6 |
| GET | `/api/inventory` | `/macro` | 6 |
| GET | `/api/fleet` | `/fleet` | 7 |
| — | — | `/track-record` | 8 |

References brief §3.2 ("Route map"). The frontend uses App Router; each
route is a directory under `app/`. Phase 1 scaffolds `/` only.

## Palette tokens

Lifted from `docs/brainstorms/ui-polish.md` (authoritative palette
table). Exposed as CSS custom properties on `:root` in
`frontend/styles/tokens.css`, then mapped into `tailwind.config.ts`'s
`theme.extend.colors`. Component code references them via
`className="bg-bg-1 text-text-primary"`.

```css
:root {
  --bg-1: #0A0E1A;
  --bg-2: #121826;
  --bg-3: #1B2232;
  --border: #2A3245;
  --text-primary: #E6EBF5;
  --text-secondary: #9AA4B8;
  --text-muted: #5B6578;
  --primary: #22D3EE;
  --primary-glow: rgba(34, 211, 238, 0.35);
  --warn: #F59E0B;
  --alert: #EF4444;
  --positive: #84CC16;
  --negative: #F43F5E;
  --gridline: rgba(255, 255, 255, 0.06);
}
```

References brief §3.3 ("Palette tokens"). Any Phase-3 UI work consumes
these names only — no raw hex in components.

## Component inventory

Phase 3 ships exactly five common components:

- `Nav.tsx` — sticky left rail on `lg:` viewport, bottom-tab bar
  below. Four routes for now: Home, Positions, Macro, Fleet. Active
  state uses `--primary`. Mobile bar height 56px, safe-area padding
  via `pb-[env(safe-area-inset-bottom)]`.
- `Footer.tsx` — reads `/api/build-info`, renders "build `sha_short` ·
  `region` · deployed `time`" plus the standing disclaimer from the
  Streamlit footer. No personalization (UI-polish correction applies).
- `LoadingSkeleton.tsx` — `animate-pulse` divs at configurable
  heights. Prop `lines?: number, height?: string`.
- `EmptyState.tsx` — centred Lucide icon + one-line copy + optional
  CTA button.
- `ErrorState.tsx` — red-tinted card, message + "Retry" button calling
  the passed `retry?: () => void`.

References brief §3.4 ("Component inventory"). Hero card, ticker tape,
and globe are **not** scaffolded in this branch — their empty routes /
placeholders exist so the Phase-4+ subagents have a landing target.

## Deploy topology

```
┌──────────────────────────┐          ┌──────────────────────────────┐
│ Azure Static Web Apps    │          │ Azure App Service (Linux)    │
│ oil-tracker-web-NNNN     │   /api/* │ oil-tracker-api-canadaeast-  │
│ (Free tier, eastus2)     │ ────────>│ NNNN   (B1, canadaeast)      │
│ Next.js 15, App Router   │  proxy   │ FastAPI, uvicorn[standard]   │
└──────────────────────────┘          └──────────────────────────────┘
          │                                        │
          │ build-info.txt                         │ /api/build-info
          ▼                                        ▼
        live-verify                              live-verify
```

References brief §3.5 ("Deploy topology") + brainstorm
"Decision defaults" 1–2. The `/api/*` proxy is configured in
`static-web-apps/staticwebapp.config.json` so the frontend's
`fetch("/api/thesis/latest")` hits the App Service without a CORS
dance. FastAPI's `CORSMiddleware` still allows the SWA origin as a
backstop for local dev + direct testing.

The resources are **not** provisioned today. The workflow has the
expected name as a placeholder env var, commented out where a real
deploy step would gate on its existence.

## SSE patterns

Streaming `POST /api/thesis/generate`:

1. Client opens a `fetch` POST with `Accept: text/event-stream` via
   `lib/sse.ts`' `postEventSource(url, body, onEvent)` helper.
2. FastAPI route returns an `EventSourceResponse` (sse-starlette) that
   yields `{event: "token", data: "<text>"}` per OpenAI chunk plus a
   final `{event: "done", data: "<json>"}` with the full thesis.
3. Client progressively updates a React state slice; on `done`, React
   Query caches the result keyed by the thesis id.
4. Disconnect handling: sse-starlette's `ping` keeps the connection
   alive; on browser reconnect the client falls back to
   `GET /api/thesis/latest`.

References brief §3.6 ("SSE patterns") + brainstorm
"Decision defaults" #5. Phase-4 subagent implements the real handler;
Phase-1 route is an echo stub.

## Migration phases (1–10)

Each phase is scoped to one subagent run, following the brief §4:

1. **Scaffold** (this branch) — repo layout, two passing tests,
   CD workflow file, three planning docs.
2. **Backend endpoints** — real `/api/spread` + `/api/thesis/latest`
   reading the same Azure Table / blob store the Streamlit app reads.
   No writes. OpenAPI surface locked.
3. **Frontend foundation** — Nav, Footer, theme provider, React
   Query client, `/api/build-info` consumer, route shells for all
   six pages. No real data yet.
4. **Hero card** — stance pill, conviction bar, instrument tiles,
   checklist, catalyst countdown. Consumes `/api/thesis/latest`. SSE
   wired for `/api/thesis/generate`.
5. **Ticker tape** — top-of-page Bloomberg strip. Consumes
   `/api/spread` (or a dedicated `/api/quotes`).
6. **Chart pages** — `/macro`: inventory + CFTC charts (Recharts).
7. **Globe** — `/fleet`: R3F globe with tanker tracks. Code-split via
   `next/dynamic`.
8. **Positions + track record** — `/positions` reads from Alpaca
   adapter (stub until P1.2 ships auth); `/track-record` reads from
   the same track-record blob the Streamlit app reads.
9. **Cutover** — DNS / subdomain flip. Static Web App aliased to
   the canonical URL. Streamlit moved to `legacy.` subdomain.
10. **Streamlit teardown** — after 30 days of parity, remove
    `cd.yml`, delete the Streamlit App Service resource, archive
    `app.py` + the presentation-only Streamlit modules.

References brief §4 ("Migration phases"). Phases 2–10 each run with
a fresh subagent per the plan doc.

## Acceptance criteria

Scaffold branch (this PR) lands green when:

- `pytest backend/tests -q` returns `2 passed` once FastAPI is
  installed. (CI installs; local sandbox run may show import errors.)
- `cd-nextjs.yml` parses as valid YAML (GitHub's YAML schema) and is
  wired to the right path filters.
- `frontend/package.json` declares every dependency the plan calls
  for; `npm ci && npm run build` passes in CI (not attempted locally).
- No change to `app.py`, `theme.py`, `language.py`, `providers/*`,
  `data_ingestion.py`, `quantitative_models.py`, or any file the
  Streamlit CD zips.
- Existing `cd.yml` is byte-identical to main.

References brief §5 ("Tests") + "Hard rules".

## Reversibility

The scaffold branch is a pure additive change. If we abandon the
migration:

- Delete the `backend/`, `frontend/`, and `static-web-apps/`
  directories.
- Delete `.github/workflows/cd-nextjs.yml`.
- Delete the three planning docs.
- No Streamlit code path changes — reversal is a `git revert` of the
  four commits on this branch.

The Streamlit app continues shipping the entire time. There is no
user-visible impact from landing this branch.

## Open questions (mirror brainstorm)

- **Q1** (custom domain): platform subdomains for Phase 1–8; custom
  domain in a Phase-9 follow-up. No code change needed until the
  flip.
- **Q2** (SWA region = eastus2): accept for Phase 1; promote to
  paid-tier canadaeast only if cross-region hop metrics warrant.
- **Q3** (Tailwind v3 → v4): revisit Q3 2026.
- **Q4** (OpenAPI codegen): hand-write TS types until the endpoint
  count exceeds ~15.
- **Q5** (SSE → WebSocket): stay on SSE; promote only if Alpaca
  bar-subscribe lands.

## Residual default

Anything mid-work that isn't covered: most-conservative, minimal,
reversible. Record in PROGRESS.md and keep moving.
