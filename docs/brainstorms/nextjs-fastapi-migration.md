# Next.js + FastAPI stack migration — Brainstorm

> **Status:** DRAFT (2026-04-23). Scaffolding branch
> `feat/nextjs-fastapi-stack` lands the repo skeleton, planning docs,
> and a parallel CD pipeline. The Streamlit app at
> `oil-tracker-app-canadaeast-4474` keeps shipping on every main push
> via the existing `.github/workflows/cd.yml` — this brainstorm does
> **not** propose retiring it until the new stack reaches visual +
> functional parity (Phase 9 cutover, documented in the plan). Two
> pipelines running side by side is the explicit intent for the
> migration window.

## The user problem, restated

The UI-polish pass landed a Bloomberg-adjacent palette on top of
Streamlit, but every demo keeps exposing the same handful of framework
ceilings that no amount of CSS injection can sand down:

1. **Rerun-on-interaction semantics.** Every widget interaction
   re-executes the full script. We pay for that with the layout
   flicker on tab switch, the "your session ended" prompt when the
   websocket blips, and the fact that a stance-pill click can't be a
   pure client-side toggle — it has to round-trip the whole data
   graph.
2. **Tab-ordering limits.** Tabs are ordered in declaration order. We
   shimmed mobile ordering via CSS `order:` properties (UX-revision
   v2), but the "Trade Thesis first on mobile" desire is still brittle
   — any new tab risks regressing mobile order because the cascade
   relies on `nth-child` selectors against Streamlit's own DOM.
3. **Chrome leaks.** Streamlit's deploy button, hamburger, and "Made
   with Streamlit" footer can be hidden with `display: none`, but the
   dev-mode toolbar reappears on every framework upgrade. The
   `MainMenu` button is marked `data-testid` but the attribute flips
   between minor releases.
4. **Mobile sidebar.** The built-in sidebar is a hard requirement for
   `st.sidebar`-based nav but unusable on <768px — it overlays content
   and can't be made a bottom-tab bar without rewriting the component
   tree.
5. **Non-overridable dev UI.** "Deploy", "Edit with IDE", and the
   GitHub Codespaces prompt appear under `STREAMLIT_ENV=prod` whenever
   the runtime is behind a reverse-proxy (Azure App Service). We've
   scripted their removal in `theme.py::inject_css`, but they surface
   when the user deep-links to routes that re-trigger the first paint.

UI polish treated these as surface-level scratches. They're structural:
the framework wasn't built for a trading terminal surface, and each
shim is one framework release from rebreaking.

## Why now

Three pulls, all stronger than they were a month ago:

- **Alpaca execution is imminent** (P1.2). Order buttons need to feel
  like Bloomberg's F9, not a `st.button` with a 400ms rerun. We've
  written enough speculative HTML-component workarounds (countdown
  pill, ticker tape) to know: we're building a SPA inside Streamlit
  one injection at a time.
- **Globe + 3D tonnage viz** shipped experimentally via
  `webgpu_components.py`. Three.js performs but the Streamlit ↔ iframe
  bridge is custom, undocumented, and breaks the session-state model
  on reload.
- **Mobile traders.** Half the visits are sub-768px. Streamlit's
  mobile story is a concession, not a product. A real mobile-first
  framework unlocks a substantial UX lift.

## Alternatives considered

### A. In-Streamlit overhaul (polish pass v3)

Keep Streamlit, triple down on CSS injection + custom components.
**Rejected — diminishing returns.** UIP already burned two weeks to
reach the current baseline. Every further gain comes at the cost of
fighting the framework: custom components mean a per-component iframe
boundary, a message-passing contract, and a state-sync layer we now
write and maintain. At some point you're writing React inside Streamlit.
Better to write React.

### B. SvelteKit + FastAPI

SvelteKit's compile-time reactivity beats React's VDOM for chart-heavy
pages; the DX for a solo dev is excellent. **Not chosen** because:

- Component ecosystem is thinner (no shadcn equivalent of the same
  depth; fewer "copy this pattern" templates for traders' surfaces).
- Three.js + Svelte is viable but less-trodden than Three.js + R3F.
- Recharts / Nivo / Tremor all target React first; we'd be porting.
- **Solo-dev leverage** is higher on the React side given Aidan's
  existing muscle memory.

### C. Remix + FastAPI

Remix's loader/action model is elegant for server-driven data; we'd
pay less plumbing tax than Next. **Not chosen** because:

- Remix merged into React Router v7 in Oct 2024. The ecosystem is
  mid-consolidation; docs churn is a tax for a solo dev.
- Azure Static Web Apps has first-class Next.js adapter support; Remix
  / RR7 support is a community shim.
- SSE on Remix requires an extra resource-route pattern vs Next's
  drop-in route handler.

### D. Plain HTMX + FastAPI templates

Lowest JS surface. Real-time via SSE. **Not chosen** because:

- Three.js globe still wants a full JS runtime — we'd end up with
  HTMX *and* a 3D bundle, worst of both.
- Client-side state for chart pans / zooms / multi-select is painful
  in HTMX — you reach for Alpine and suddenly you have two frameworks.
- We'd be rebuilding the grid + card primitives from scratch (no
  shadcn).

### E. Next.js 15 + FastAPI (chosen)

Server Components keep the SSR/DX win; `use client` islands carry the
interactive charts and globe. Route Handlers give a thin SSE surface
to the Python backend when we don't want the proxy. FastAPI keeps the
existing Python modules (`trade_thesis.py`, `providers/*.py`,
`thesis_context.py`) as first-class — the backend becomes a thin
adapter layer, not a rewrite. **Winning because:**

- Ecosystem density (shadcn, Radix, Recharts, R3F, framer-motion) —
  every trader-UX pattern has a reference implementation to crib.
- Azure Static Web Apps free tier + `Azure/static-web-apps-deploy@v1`
  removes a class of infra headaches.
- FastAPI reuses the exact Python modules we've shipped. No
  re-implementation of cointegration, quant models, provider glue.
- SSE for `/api/thesis/generate` streaming is ~10 lines (sse-starlette).
- Reversibility: if this fails, the Streamlit app is still live,
  unmodified, at the existing URL.

## Decision defaults

Aidan's brief picks defaults for every fork. One open-question flag
per uncertainty area.

1. **Backend runtime = Azure App Service, Linux, Python 3.11.**
   Same region (`canadaeast`), same RG (`oil-price-tracker`).
   Resource name pending: `oil-tracker-api-canadaeast-NNNN` (the
   4-digit suffix is the same convention as the Streamlit app).
   **Open question 1:** should the backend and frontend share a
   custom domain (`api.` + `www.`) or stay on azurewebsites.net +
   *.azurestaticapps.net? Proposed default: platform subdomains for
   now, custom domain in a follow-up when Alpaca ships.

2. **Frontend runtime = Azure Static Web Apps, free tier.**
   Bundled GitHub OIDC + automatic PR preview environments. Canadian
   region is not offered on free tier — closest is `eastus2`;
   negligible latency (<30ms from canadaeast backend).
   **Open question 2:** accept eastus2 for the SWA region, or go to
   the paid tier for canadaeast? Proposed default: accept eastus2,
   revisit if the cross-region backend hop shows up in real metrics.

3. **Tailwind v3.4 (not v4).** shadcn/ui and most copy-paste
   component templates are still 3.x. Revisit when ecosystem
   consensus moves.
   **Open question 3:** upgrade path to v4? Proposed default: revisit
   Q3 2026 when shadcn ships v4-native templates.

4. **React Query + fetch wrapper, not tRPC.** Python backend makes
   tRPC a non-starter unless we add a codegen step. OpenAPI + `orval`
   is the fallback if hand-written type definitions drift.
   **Open question 4:** generate TS types from FastAPI's OpenAPI? Proposed
   default: hand-write for Phase 1–3 (small surface), codegen when
   the endpoint count crosses ~15.

5. **SSE over WebSocket for streaming thesis.** SSE is one-way,
   which is all we need; HTTP/1.1 works through App Service without
   a separate config; retry-on-disconnect is built in.
   **Open question 5:** promote to WebSocket if we ever add
   client→server live events? Proposed default: SSE now, WebSocket
   only if Alpaca bar-subscribe lands and we want to multiplex.

## Risks

- **Cutover complexity.** Two live apps + a cutover (Phase 9) is
  where migrations die. Mitigation: phased DNS flip, keep Streamlit
  alive behind an alternate subdomain for ≥30d after cutover.
- **Bundle bloat.** Three.js + Recharts + framer-motion + Radix can
  hit 400KB gzipped without care. Mitigation: code-split per route,
  `next/dynamic` for the globe, visual budget in the design spec.
- **Solo-dev divergence.** Two codebases in the migration window
  means every fix happens twice. Mitigation: feature-freeze Streamlit
  during the migration window — only hot-fixes land on it.
- **Provider auth.** Alpaca OAuth + the user-store Phase 2 work
  assumes Streamlit's session model; the FastAPI port will re-home
  both. The session-management shape moves from in-framework to a
  backend-signed-cookie or JWT model. Mitigation: design spec pins
  the session-shape decision up front.

## Reversibility

If the new stack fails (App Service cost spike, SSE weirdness at the
App Service Ingress layer, DX regressions), we freeze the Next/FastAPI
stack, keep routing traffic to the Streamlit app, and revisit in Q3.
The Streamlit code never disappears until Phase 10 teardown, which is
explicitly gated on 30 days of parity on the new stack.

## Side-by-side pipelines

For the duration of the migration window:

- `.github/workflows/cd.yml` (existing, untouched) deploys Streamlit to
  `oil-tracker-app-canadaeast-4474` on every push to main.
- `.github/workflows/cd-nextjs.yml` (new, this branch) deploys the
  FastAPI backend to `oil-tracker-api-canadaeast-NNNN` and the Next.js
  frontend to a new Static Web App — but only when the push touches
  `backend/**`, `frontend/**`, or the workflow itself.

The path-filter on the new workflow means Streamlit changes don't
trigger new-stack deploys and vice versa. Both pipelines stamp
build-info; both pipelines live-verify by polling a build-info asset.

## Pending provisioning — "Waiting on Aidan"

DO NOT provision today. Document the expected resources so the
backend-endpoints subagent can take them over cleanly once Aidan
greenlights:

- **Backend App Service** — name `oil-tracker-api-canadaeast-NNNN`
  (Aidan picks suffix), SKU B1 to match Streamlit, Linux Python 3.11,
  RG `oil-price-tracker`, region `canadaeast`. `az webapp create
  --name oil-tracker-api-canadaeast-NNNN --resource-group
  oil-price-tracker --plan <plan-name> --runtime "PYTHON|3.11"`.
- **Static Web App** — name `oil-tracker-web-NNNN`, free tier, region
  `eastus2` (no canadaeast on free). `az staticwebapp create --name
  oil-tracker-web-NNNN --resource-group oil-price-tracker --location
  eastus2 --sku Free`.
- **Secrets** — same OIDC federation the existing pipeline uses
  (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`) gets
  a second federated credential against the new subjects. Static Web
  Apps emits `AZURE_STATIC_WEB_APPS_API_TOKEN` via portal; park in
  repo secrets once the SWA exists.

## Residual default

Anything that surfaces mid-work and isn't covered: most-conservative,
minimal, reversible. Record in PROGRESS.md and move on.
