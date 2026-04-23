# Next.js + FastAPI stack migration — Plan

> **Status:** DRAFT (2026-04-23).
> **Branch:** `feat/nextjs-fastapi-stack` off `main`, worktree at
> `../macro_oil_terminal-nextjs`.
> **Rhythm:** fresh subagent per phase (Phases 2–10), RED→GREEN→
> REFACTOR→COMMIT per sub-task inside a phase. Phase 1 (this branch)
> lands as four chunked commits, not per-task commits, because every
> piece depends on the phase arriving together.

## Definition of done — whole migration

- Next.js 15 frontend live at `oil-tracker-web-NNNN.azurestaticapps.net`
  (later: custom domain) with visual parity to the Streamlit app.
- FastAPI backend live at `oil-tracker-api-canadaeast-NNNN.azurewebsites.net`
  serving every surface the Streamlit app reads today.
- 30 days of parity metrics captured in `docs/perf/nextjs-cutover.md`.
- Streamlit app torn down; `cd.yml` removed; legacy modules archived.

## Definition of done — this branch (Phase 1)

- `docs/brainstorms/nextjs-fastapi-migration.md`,
  `docs/designs/nextjs-fastapi-migration.md`, and this plan are
  checked in.
- `backend/` scaffolded with two passing pytest targets, router
  stubs, pydantic v2 models, a `main.py` app factory.
- `frontend/` scaffolded as if from `npx create-next-app@latest
  --typescript --tailwind --app --use-npm` minus `node_modules`.
- `static-web-apps/staticwebapp.config.json` routes `/api/*` to the
  backend.
- `.github/workflows/cd-nextjs.yml` checks in; `.github/workflows/cd.yml`
  is untouched.
- Four chunked commits pushed to `feat/nextjs-fastapi-stack`. No merge.

---

## Phase 1 — Scaffold (this branch)

**Red → Green → Refactor → Commit, four commits total:**

1. `docs(arch): brainstorm + design + plan for Next.js + FastAPI stack`
2. `feat(backend): FastAPI scaffold + /health + /api/build-info + tests`
3. `feat(frontend): Next.js 15 app-router scaffold + Tailwind tokens + Nav/Footer/states`
4. `ci: cd-nextjs workflow — dual-target deploy (App Service + Static Web Apps)`

Push `-u origin feat/nextjs-fastapi-stack`. Do NOT merge. Leaves the
branch for the Phase-2 subagent.

---

## Phase 2 — Backend endpoints

**Target:** real implementations of `/api/spread`, `/api/thesis/latest`
against the same data sources the Streamlit app reads today.

**Files:**
- Modify: `backend/routers/spread.py`, `backend/routers/thesis.py`,
  `backend/services/spread_service.py`,
  `backend/services/thesis_service.py`, `backend/models/thesis.py`,
  `backend/models/spread.py`.
- Create: `backend/tests/test_spread.py`, `backend/tests/test_thesis.py`.

**Red** — tests for `GET /api/spread` returning a
`{series: [{date, spread, zscore}, ...]}` payload and
`GET /api/thesis/latest` returning a `Thesis` schema with
`plain_english_headline`, `stance`, `confidence`, `instruments[]`,
`checklist[]`. Mock the service layer so the test doesn't touch Azure.

**Green** — wire services to the existing Python modules via a thin
import: `from trade_thesis import latest_thesis` (re-exported from
the Streamlit repo root, which the deploy packaging already
includes). Services stay stateless.

**Refactor** — consolidate Pydantic schemas under `backend/models/`,
remove duplication between Streamlit dataclasses + Pydantic models
by re-using dataclass fields via `TypeAdapter.validate_python`.

**Commit:** `feat(backend): wire /api/spread and /api/thesis/latest to live services (phase 2)`.

**Subagent pointer (this is what the next run targets):**
> Start at `backend/services/spread_service.py` — import the existing
> `cointegration.compute_spread_series` and shape it into the
> pydantic schema. Do NOT rewrite the cointegration logic. If the
> import path is awkward, add a `backend/services/_compat.py` to
> hide `sys.path` gymnastics in one place.

---

## Phase 3 — Frontend foundation

**Target:** Nav, Footer, Providers, route shells, React Query client,
tokens honoured through Tailwind. No real data yet; every page uses
`EmptyState`.

**Files:**
- Modify: `frontend/app/layout.tsx`, `frontend/app/page.tsx`,
  `frontend/components/common/*`, `frontend/lib/api.ts`.
- Create: `frontend/app/positions/page.tsx`,
  `frontend/app/macro/page.tsx`, `frontend/app/fleet/page.tsx`,
  `frontend/app/track-record/page.tsx`.
- Create: `frontend/__tests__/Nav.test.tsx` (vitest + testing-library).

**Red** — tests for `Nav` rendering all four links, `Footer`
rendering build-info from a mocked fetch, `EmptyState` accepting a
CTA.

**Green** — implement components.

**Refactor** — pull common layout into `app/(marketing)/layout.tsx` if
the pattern repeats.

**Commit:** `feat(frontend): Nav + Footer + route shells + React Query client (phase 3)`.

**Subagent pointer:**
> Start at `frontend/components/common/Nav.tsx`. Use `usePathname()`
> for active state. Mobile bar is `fixed bottom-0 inset-x-0
> pb-[env(safe-area-inset-bottom)]`. Desktop rail is `hidden lg:flex`.

---

## Phase 4 — Hero card

**Target:** pixel-parity port of the Streamlit hero band. Stance pill,
plain-English headline, conviction bar, instrument tiles (Paper / ETF
/ Futures), pre-trade checklist, catalyst countdown. SSE wired to
`/api/thesis/generate` so "Regenerate" streams tokens.

**Red → Green → Refactor → Commit, per sub-component:**

- 4a `HeroCard` scaffolding + skeleton
- 4b `StancePill` + `ConvictionBar`
- 4c `InstrumentTiles`
- 4d `Checklist`
- 4e `CatalystCountdown`
- 4f `RegenerateButton` (SSE)
- 4g visual-regression snapshots, desktop + mobile

**Commit (squashed):** `feat(frontend): hero card with SSE regeneration (phase 4)`.

**Subagent pointer:**
> Reference is `app.py::render_hero_trade_idea()` and every helper it
> calls from `theme.py`. The target markup is the same — the
> framework is the only thing that changes.

---

## Phase 5 — Ticker tape

**Target:** horizontal auto-scrolling strip of live quotes above the
hero card. 12 tickers. Pauses on hover. Accessible label per quote.

**Commit:** `feat(frontend): ticker tape component (phase 5)`.

**Subagent pointer:**
> Reference is `theme.py::render_ticker_strip` + the ticker css in
> `theme.inject_css`. Next.js version uses framer-motion for the
> scroll animation instead of CSS keyframes to allow pause-on-hover.

---

## Phase 6 — Chart pages

**Target:** `/macro` route with CFTC commitments + inventory + PADD
charts using Recharts. `/macro` is a grid of cards; each card owns one
chart component.

**Commit:** `feat(frontend): macro chart page with Recharts (phase 6)`.

**Subagent pointer:**
> Three data endpoints (`/api/cftc`, `/api/inventory`, dedicated
> `/api/padd`). Use React Query with a 5-minute `staleTime` — the
> Streamlit equivalent caches for the same window.

---

## Phase 7 — Globe

**Target:** `/fleet` route with a Three.js + React Three Fiber globe
showing tanker tracks. Code-split via `next/dynamic` to keep the home
bundle < 200KB.

**Commit:** `feat(frontend): fleet globe with R3F (phase 7)`.

**Subagent pointer:**
> Reference is `webgpu_components.py` — the geometry is already
> computed there. Port the lat/lng → 3D math; replace the iframe
> bridge with an R3F scene under `components/fleet/Globe.tsx`.

---

## Phase 8 — Positions + track record

**Target:** `/positions` (requires auth — stubbed until P1.2) and
`/track-record` (public) routes consuming Alpaca + track-record
endpoints.

**Commit:** `feat(frontend): positions + track record pages (phase 8)`.

**Subagent pointer:**
> Auth flow is out of scope — ship the UI against mock data with a
> `MOCK_AUTH_USER` env flag mirroring the Streamlit pattern.

---

## Phase 9 — Cutover

**Target:** DNS / subdomain flip. New stack is canonical. Streamlit is
aliased to `legacy.*`. Both deploys keep running for the 30-day
observation window.

**Steps (no code, mostly Azure ops):**

1. Create custom-domain binding on the Static Web App.
2. Create custom-domain binding on the FastAPI App Service.
3. Update DNS `CNAME` records.
4. Alias Streamlit App Service to `legacy.*` subdomain.
5. Update `.github/workflows/cd.yml`'s health check to hit the legacy
   URL.

**Commit:** `ops(cutover): flip DNS to new stack (phase 9)`.

---

## Phase 10 — Streamlit teardown

**Gate:** 30 days of new-stack parity, zero rollback events, Aidan's
explicit greenlight.

**Steps:**

1. Delete `.github/workflows/cd.yml`.
2. Archive `app.py`, `theme.py`, `language.py`, `webgpu_components.py`,
   and the Streamlit-only providers under `legacy/streamlit/`.
3. `az webapp delete --name oil-tracker-app-canadaeast-4474`.
4. Update README to point at the new stack.

**Commit:** `ops(teardown): retire Streamlit app (phase 10)`.

---

## Rollback plan per phase

Every phase is independently revertable because each phase commits on
its own feature branch off main, squash-merges, and lands in order.
Rolling back phase N requires only `git revert <merge-sha>` + a
redeploy — the plan never shares mutable state across phases in
production (data stays in Azure Table Storage, read-only from the
backend's perspective until P1.2).

## Risk register

- **R1 — pip install fails in sandbox.** Mitigation: don't run pip
  locally; let CI install. Workflow's test gate catches install
  failures early.
- **R2 — npm install fails in sandbox.** Same mitigation — `npm ci`
  runs in CI only.
- **R3 — OIDC federation credential not configured for new subject.**
  Mitigation: brainstorm documents the expected `az ad app federated-credential
  create` command; subagent provisioning Phase 2 backend resources
  also provisions the federated cred.
- **R4 — Cross-origin cookie issues when Alpaca auth lands.**
  Mitigation: Phase 1 uses Static Web Apps' `/api/*` proxy so the
  same-origin invariant holds from day one.
- **R5 — Bundle bloat.** Mitigation: per-route code-splitting, visual
  budget in design spec, `next build` `--profile` numbers checked
  against budget in the Phase-7 commit.

## Residual default

Anything mid-work that isn't covered: most-conservative, minimal,
reversible. Record in PROGRESS.md and keep moving.
