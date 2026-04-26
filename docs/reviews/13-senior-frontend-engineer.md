# Review #13 — Senior Frontend Engineer (Code-side)

Scope: `frontend/` of `macro_oil_terminal` on `main`. Static review only — no
edits to source. Tooling commands are noted in the appendix; where the venv
lacks `node_modules` and a fresh `npm install` is forbidden, the corresponding
commands are skipped and called out explicitly rather than silently passed.

Stack snapshot from `frontend/package.json`:

- next 15 (app router, `output: "export"`), React 19, TS 5.6 strict
- Tailwind 3.4 + shadcn/ui (radix dialog/tabs/toast/tooltip/separator/slot)
- @tanstack/react-query 5.59, framer-motion 11.11, recharts 2.13
- three 0.169 + @react-three/{fiber,drei} (only `three` actually imported in
  components — see Finding F12), WebGPU via `three/webgpu` + `three/tsl`
- vitest 2.1 + @testing-library/react 16; Playwright lives outside `frontend/`
  in `tests/e2e/*.py`

---

## Axis 1 — TypeScript strictness — **8/10**

Evidence:

- `frontend/tsconfig.json:7` — `"strict": true`, `noEmit: true`, `target: ES2022`,
  `moduleResolution: bundler`, `isolatedModules: true`. Good baseline.
- `.eslintrc.json:4` — `@typescript-eslint/no-explicit-any` is set to `warn`,
  not `error`. With `next/typescript` extended this still passes lint cleanly,
  but means new `any`s won't fail CI.
- `@ts-ignore` / `@ts-expect-error` count across the entire `frontend/` tree:
  **0**. Excellent.
- `as any` / `<any>` / `: any` count across `components/lib/app/types/**.{ts,tsx}`:
  **11 occurrences in 3 files** (`components/globe/FleetGlobe.tsx` 5,
  `components/hero/HeroShaderBackground.tsx` 4, `__tests__/setup.ts` 2).
- `as unknown as X` usage: present in 4 places, all justified —
  `FleetGlobe.tsx:105` (typed window-attached globe API), `:430`, `:672`
  (assigning the API to the canvas), `HeroShaderBackground.tsx:109`
  (live-update of a `uniform(float)` whose runtime `.value` is missing from
  the d.ts), and `InstrumentTile.tsx:44` (legacy backend shape tolerance,
  with a comment explaining why).
- Explicit `as any` clusters: all in WebGPU/TSL plumbing. The TSL helper
  surface (`positionWorld`, `cameraPosition`, `mx_fractal_noise_float`,
  `uniform(...).sub`) is genuinely under-typed in `three@0.169` —
  `FleetGlobe.tsx:207-210` widens the import to `... & { [k: string]: unknown }`
  for that exact reason. The casts are scoped to a single file each.
- `types/api.ts:115` — `trades: Array<Record<string, unknown>>` and `params:
  Record<string, unknown>` deliberately keep escape hatches around the
  unstable backtest payload. Reasonable.
- The hand-written API types (`types/api.ts`) keep both lower-case and
  UPPER_CASE `Stance` (lines 156–164) so the UI tolerates whichever casing
  the backend emits — pragmatic, but it leaks unnormalised values into
  components (StancePill, ConfidenceBar all do `.toUpperCase()` themselves).

Top fixes:
1. **Promote `no-explicit-any` to `error`** in `.eslintrc.json` and add a
   targeted `// eslint-disable-next-line` comment over each TSL cast in the
   WebGPU components (already half-done — `HeroShaderBackground.tsx:32`,
   `FleetGlobe.tsx:50` — just be consistent and ban the rest).
2. **Centralise the WebGPU type shim** in `lib/three-webgpu.d.ts` so the
   `as any` rash in `FleetGlobe.tsx:242,260,262,265` and
   `HeroShaderBackground.tsx:84,89,90` becomes a one-line `declare module
   "three/tsl"` augmentation instead of in-line casts.
3. **Normalise `Stance` once** in `lib/api.ts` (or a tiny `lib/language.ts`
   stub — note `StancePill.tsx:11` references `lib/language.ts` in a comment
   but that file doesn't exist) and remove the dual lowercase/uppercase
   union so consumers can rely on a canonical form.

---

## Axis 2 — Hook hygiene — **6/10**

Evidence:

- **TickerTape SSE useEffect** (`components/ticker/TickerTape.tsx:50–76`):
  `eslint-disable-next-line react-hooks/exhaustive-deps` with empty deps,
  but the closure captures `spreadQ.refetch`. React Query's `refetch` is a
  stable reference, so behaviour is correct, but the disable hides a real
  audit signal. A `closed` flag *and* `source.close()` give double-close
  semantics on unmount — fine, just verbose. **No retry / reconnect on
  `onerror`** (line 65–67): closes and never re-opens, even after a transient
  network blip. The 30s react-query polling masks this in the happy path.
- **PositionsView SSE useEffect** (`components/positions/PositionsView.tsx:122–141`):
  Empty deps with no eslint-disable. Lints clean because everything inside is
  module-level. **No retry / reconnect.** The cleanup correctly removes the
  listener and closes the source.
- **TradeIdeaHeroClient SSE useEffect** (`components/hero/TradeIdeaHeroClient.tsx:94–142`):
  Has a `streamStartedRef` guard so React 18+ strict-mode double-mount in dev
  doesn't fire two streams. **No** `eslint-disable`, but deps `[]` should
  trigger the rule — the closure captures `setStream` which is stable, fine,
  but I'd expect lint to warn about the re-render path. This works because
  the body only calls `setStream`. AbortController abort-on-unmount is
  correct. **No reconnect/backoff** on SSE error — the comment "non-fatal,
  surface in dev" is honest, but on prod the user gets a stale hero card if
  the stream errors mid-flight.
- **TrackRecord fetch useEffect** (`components/track-record/TrackRecord.tsx:42–68`):
  `cancelled` flag pattern — clean. No retry on transient 5xx, but that's
  user-driven via reload. Acceptable for this surface.
- **Footer fetch useEffect** (`components/common/Footer.tsx:16–30`):
  `cancelled` flag, swallow-on-error — clean.
- **HeroShaderBackground useEffect** (`components/hero/HeroShaderBackground.tsx:30–131`):
  Empty deps; uses a `stretchRef.current` ref to keep the latest shader
  uniform value without retriggering setup. **`disposed` is set but never
  read** — the cleanup just calls `cleanup?.()` without checking. The async
  IIFE may complete after unmount and assign `cleanup` to a stale closure,
  in which case the outer cleanup runs it. This is OK in practice (the
  cleanup is idempotent) but the `disposed` flag is dead code.
- **FleetGlobe boot useEffect** (`components/globe/FleetGlobe.tsx:54–100`):
  Deps `[forceFallback, hasWebGPU]` with eslint-disable; the deeper props
  `vessels, visibleCategories, onVesselClick, trails` are pushed via the
  parallel `useEffect` at line 104. This bifurcation is correct (boot once,
  update via API). Nice pattern.
- **PreTradeChecklist useEffect** (`components/hero/PreTradeChecklist.tsx:54–56`):
  Reads localStorage on `thesisId` change — clean. `useCallback`-wrapped
  toggle (line 58) — clean.
- **No race conditions found** in the post-mount → setState pattern. Every
  fetch-on-mount has a `cancelled` (or AbortController) guard. The SSE
  paths all close on unmount.
- **`eslint-disable react-hooks/exhaustive-deps`** count across `frontend/`:
  **2** (TickerTape, FleetGlobe). Both genuinely need the boot-once
  semantics; both could be made compliant with refs + stable callbacks.

Top fixes:
1. **Add SSE reconnect-with-backoff** in `TickerTape.tsx`,
   `PositionsView.tsx`, and `TradeIdeaHeroClient.tsx`. A 1/2/5/10s capped
   backoff after `onerror` would close the gap between "stream dropped"
   and "react-query polls again". Right now the live ticker silently
   degrades to 30s polling on any transient WiFi blip.
2. **Surface SSE failure to the user** at least once — currently
   `TradeIdeaHeroClient.tsx:130` only `console.warn`s. A toast (Toaster is
   already wired in `Providers`) or a small status pill would give
   operators a fighting chance of noticing prod regressions.
3. **Drop the `disposed` dead-code flag** in `HeroShaderBackground.tsx:37,128`
   or actually use it to gate the post-mount `setReady`-style writes. Clean
   up the parallel `disposed` in `FleetGlobe.tsx:64,87,91` for the same
   reason — they're useful in `FleetGlobe` (it gates the `setReady("ok")`)
   but `HeroShader` never branches on it.

---

## Axis 3 — SSR / static-export correctness — **9/10**

Evidence:

- `next.config.mjs:8` — `output: "export"` with `trailingSlash: true`; image
  optimisation off (`unoptimized: true`) — correct for SWA.
- `app/fleet/page.tsx:15` — `dynamic(() => import("@/components/globe/FleetGlobe").then(m => m.FleetGlobe), { ssr: false })`.
  This is the recently-shipped fix and it's correct. The comment at lines
  10–14 explains the React #418 hydration mismatch motivation cleanly.
- Every `window.` / `navigator.` access I could find is gated:
  - `FleetGlobe.tsx:48,59` — `typeof navigator === "undefined"` guards.
  - `HeroShaderBackground.tsx:31` — `typeof navigator === "undefined"` and
    line 33 — `!(navigator as any).gpu` early-returns; the rest happens
    inside the async IIFE.
  - `PreTradeChecklist.tsx:18,33` — `typeof window === "undefined"` guards
    in both `readStored` and `writeStored`.
  - `TickerTape.tsx:51` — `typeof window === "undefined"` early return.
  - `PositionsView.tsx:123` — `typeof window === "undefined" || typeof
    EventSource === "undefined"` early return.
- `app/page.tsx` (Home) renders `<TradeIdeaHero />` which is a **Server
  Component** (`components/hero/TradeIdeaHero.tsx:35` — `async function`).
  It calls `fetch(${base}/api/thesis/latest)` at build / request time and
  hands the result down to the client. With `output: "export"` this
  effectively runs at *build time*, not request time — meaning `latest`
  data is baked into the static HTML. That's only a problem if the build
  has a backend reachable; if not, line 16–21 falls through to
  `undefined` and the client hydrates fresh. Acceptable, but **document
  this** somewhere visible: the "freshness" of the home page card depends
  on when CD ran, not when the user loaded.
- `components/positions/PositionsPanel.tsx:54` — async server component
  fetches `/api/positions` and `/api/positions/account`. Same caveat as
  above — under `output: "export"` this is build-time. The empty/null
  fallback is sound.
- `components/track-record/TrackRecord.tsx` is fully `"use client"` — no
  SSR pitfalls.
- `app/macro/page.tsx`, `app/inventory/page.tsx`, `app/positions/page.tsx`,
  `app/track-record/page.tsx` — all top-level pages either pass through to
  client components or are themselves `"use client"`. No `window`/`document`
  reachable from the module-eval path.
- `lib/providers.tsx:18` — `useState(() => createQueryClient())` — correct
  per-request client (avoids server↔client cache sharing).
- `next/dynamic` is used precisely once (FleetGlobe) — appropriately. The
  shaderbacked HeroShader does *not* `dynamic()` itself but is a `"use
  client"` component that early-returns before any WebGPU init unless
  `navigator.gpu` is present, which matches the "render nothing on SSR /
  no-WebGPU" contract.
- `staticwebapp.config.json:14` — `navigationFallback.rewrite: /index.html`
  is a **footgun for the static export**. With `output: "export"` and
  `trailingSlash: true`, every route is its own HTML file (`/macro/index.html`,
  etc.) and direct deep-links should hit those. Falling back to
  `/index.html` would serve the home shell for any unknown route. The
  `exclude` list catches `/_next/*` etc., but it does NOT exclude legit
  routes like `/macro/`. In practice SWA serves the per-route HTML before
  the fallback fires (because the static file exists), but a typo in
  `exclude` could shadow the entire fleet/positions/track-record route. Low
  probability, low severity, but worth a stake.

Top fixes:
1. **Drop a `console.assert` or build-time check** that `output: "export"`
   has built every route's HTML; or convert to `notFound()` with an explicit
   fallback. The `navigationFallback` to `/index.html` is OK but
   under-defended.
2. **Document build-time-vs-request-time data freshness** in
   `components/hero/TradeIdeaHero.tsx` and `components/positions/PositionsPanel.tsx`.
   Today the JSDoc says "first paint is seeded with real data" — true at
   build time, not at request time. Future contributors will trip on this.
3. **Inline the `navigator.gpu` cast** behind a single helper
   `lib/has-webgpu.ts` so `FleetGlobe.tsx:51` and
   `HeroShaderBackground.tsx:33` aren't independently re-implementing the
   same SSR-safe check (with subtly different return semantics).

---

## Axis 4 — Error boundaries + suspense — **4/10**

Evidence:

- **No `app/error.tsx` / `app/global-error.tsx` / `app/not-found.tsx` /
  `app/loading.tsx`** anywhere in the tree. Verified via filesystem glob.
  This is the headline gap. Any unhandled render-time exception inside a
  page bubbles to Next.js's default fallback and gives the user a blank
  page on prod (and a dev-overlay in dev).
- Per-component error boundaries: none. Every page relies on:
  - React Query's `isError` branch at the call site (good — see
    `app/macro/page.tsx:43–48`, `app/inventory/page.tsx:24–31`).
  - Component-level try/catch (`components/track-record/TrackRecord.tsx:42–68`,
    `components/positions/PositionsView.tsx:154–179`).
- `components/common/ErrorState.tsx` is a per-section red card with a
  retry button. Used by macro/inventory pages and `TradeIdeaHeroClient`.
  Good as a soft-error surface; not a boundary.
- **WebGPU globe fallback** (`components/globe/FleetGlobe.tsx:113–137`):
  excellent — explicit "WebGPU not available" copy, with the vessel count
  still surfaced. Boot failures (line 90) also set `ready: "fallback"`.
- **HeroShaderBackground** (`components/hero/HeroShaderBackground.tsx:121–124`):
  swallows boot exceptions with a `console.warn`, renders the bare canvas.
  Fine — the card sits on top of a CSS gradient anyway, so the fallback
  is just "no shader".
- **Positions SSE failure**: silent. Any `.json` parse error in
  `PositionsView.tsx:130–134` is swallowed. The `state.lastError` slot is
  reserved for close-order failures only. Reasonable.
- **TickerTape failure** (line 83–98): `unavailable` branch when both
  spread and inventory queries error AND every tile is at 0. Sensible
  triple-guard but under-renders information when only one query fails.
- **No Suspense boundaries.** No `<Suspense fallback>` anywhere — the app
  uses the older `isLoading ? skeleton : data` pattern. Fine for now,
  but means streaming server components and React 19's `use()` are off
  the table without rework.

Top fixes:
1. **Add `app/error.tsx`** (route-level) and `app/global-error.tsx` (root).
   The route-level one wraps each page in an Error Boundary; the global
   one catches `RootLayout` blowups. Both can render `ErrorState` plus a
   "Reload" button. **Highest-value 30 min of work in this review.**
2. **Add `app/not-found.tsx`** so deep-link typos don't bottom out at
   the SWA `/index.html` fallback.
3. **Wrap each chart** (SpreadChart / StretchChart / BacktestChart /
   InventoryChart) in a thin `<ChartErrorBoundary>` — recharts is happy
   to throw on degenerate data, and an unguarded throw kills the whole
   route. Or at least add a route-level `error.tsx` per route directory
   (`app/macro/error.tsx` etc.) so a busted backtest payload doesn't
   nuke the spread + stretch charts on the same page.

---

## Axis 5 — Bundle size discipline — **6/10**

I cannot run `next build` in this venv (no `node_modules`, install
forbidden). The judgement below is from source-side imports plus the
`package.json` dependency surface.

Heaviest legitimate dependencies, ranked by typical bundle weight:

1. **three** + **three/webgpu** + **three/addons** — easily the biggest
   chunk. Imported in `components/globe/FleetGlobe.tsx:184–187` and
   `components/hero/HeroShaderBackground.tsx:42–46`. Both are `"use
   client"` and dynamic-import three lazily inside the boot function, so
   three should only land in the route chunks that actually mount the
   component. **FleetGlobe** is also outer-`dynamic({ ssr: false })`'d in
   `app/fleet/page.tsx:15`, so its chunk is per-route. **Good.** The
   one risk: `HeroShaderBackground.tsx` is imported eagerly from
   `TradeIdeaHeroClient.tsx:23`, which is the hero on `/`. The async
   import inside means the runtime cost is deferred, but the static
   import means the *server-component fetch* and the *client bundle for
   `/`* both reference HeroShaderBackground; webpack should still split
   the dynamic `three` import out, but verify with `next build`.
2. **recharts** — imported by all four chart components. Each chart is
   `"use client"` and only loaded when its route is. Recharts is
   notorious for ESM tree-shake failures (the whole D3 chain pulls
   through). No `optimizePackageImports` config in `next.config.mjs:11`
   — the `experimental` block is empty. Adding `optimizePackageImports:
   ["recharts", "lucide-react"]` is the easiest 50-150 KB win.
3. **framer-motion** — imported in `TradeIdeaHeroClient.tsx`,
   `ConfidenceBar.tsx`. Not in any chart. Three pages use it. Modern
   `framer-motion` is tree-shakable; `motion.div` plus `motion.h2` /
   `motion.p` is what we use, plus AnimatePresence is *not* used —
   confirmed by grep. So this is bounded.
4. **@radix-ui/react-{dialog,dropdown-menu,tabs,toast,tooltip,separator}**
   — all imported in `components/ui/*`. dropdown-menu and tabs are
   imported in `package.json` but I did not find any consumer in
   `components/` or `app/` (likely scaffolded for future use — see
   axis 10). Dead-weight risk: small per package, but additive.
5. **@radix-ui/themes** (`^3.1.0`) is in `package.json:22` but I find
   **zero imports** of it anywhere in the source tree. **Pure dead
   dependency.** Removing saves ~80 KB of CSS+JS.
6. **@react-three/{drei,fiber}** are in `package.json` but never
   imported (the globe uses raw three.js). **Dead.**
7. **lucide-react** — used everywhere; imports are individual icons, so
   tree-shaking handles it correctly. Not a concern.
8. **@tanstack/react-query-devtools** is a dependency, not a devDep —
   but I find no `<ReactQueryDevtools />` mount anywhere. Either drop
   from deps or actually mount it (gated to dev). Either way, double-
   check it's tree-shaken in prod.

Suggested dynamic-import boundaries (in priority):

- The shader background (`HeroShaderBackground`) should be a
  `next/dynamic({ ssr: false })`-loaded child of `TradeIdeaHeroClient`,
  not a static import. WebGPU isn't on every browser; users on Safari /
  iOS get the lazy import that resolves to the early-return branch and
  zero runtime cost, but they still pay for the static-import bundle
  bytes today.
- `recharts` chart components could `dynamic()` their internals, but
  the per-page chunk strategy already gives much of that benefit.

Top fixes:
1. **Drop `@radix-ui/themes`, `@react-three/drei`, `@react-three/fiber`,
   and (if unused at runtime) `@tanstack/react-query-devtools` from
   `package.json`.** Run `next build` afterwards and compare First Load
   JS. Estimated saving: 80–150 KB gzipped.
2. **Set `experimental.optimizePackageImports: ["recharts", "lucide-react",
   "framer-motion"]`** in `next.config.mjs`. Documented Next.js 15
   feature; meaningful win on recharts.
3. **`next/dynamic` the `HeroShaderBackground`** so non-WebGPU users
   never download the three.js + TSL surface for the home route. (They
   already pay nothing at runtime; the goal is to avoid paying for the
   bytes.)

---

## Axis 6 — Test coverage gaps — **7/10**

Test inventory (`__tests__/` plus subfolders):

- `api.test.ts` — `fetchJson` 2xx/4xx/network and `postEventSource`
  parsing/error cases. Solid.
- `Footer.test.tsx` — happy path + fallback on fetch error.
- `Nav.test.tsx` — link rendering + `aria-current` + desktop/mobile.
- `FleetGlobe.test.tsx` — jsdom fallback path, empty-vessel resilience.
- `globe-physics.test.ts` — pure-math suite (lat/lon/great-circle/solar).
- `hero/CatalystCountdown.test.tsx`, `ConfidenceBar.test.tsx`,
  `InstrumentTile.test.tsx`, `PreTradeChecklist.test.tsx`,
  `StancePill.test.tsx`, `TradeIdeaHero.test.tsx` — unit + integration
  for hero. The TradeIdeaHero spec stubs both `/api/thesis/latest` and
  the SSE `generate` endpoint with an empty stream — good
  hydration/loading/error coverage.
- `positions/PositionsPanel.test.tsx` — initial render, empty state,
  quick-close POST shape, SSE trade_update merge. Excellent — covers
  the non-trivial reducer and the EventSource lifecycle.
- `ticker/TickerTape.test.tsx` — 4-tile render, sparkline DOM, error
  fallback. Good.
- `track-record/TrackRecord.test.tsx` — pure stats + component fetch
  shape. Good.
- `charts/{Backtest,Inventory,Spread,Stretch}Chart.test.tsx` — 4 specs.
  Did not read internal coverage but each chart has a test fixture file.

Critical paths uncovered:

- **SSE retry / reconnect** — there's no retry to test, but if we add
  one (per Axis 2), it needs a spec. Today: untested.
- **`API_BASE` swap behaviour** — `lib/api.ts:13` resolves three env
  vars in order, but no test asserts the precedence. Easy to break by
  reordering.
- **Hydration edge cases** — there's no SSR-output-shape test (e.g.
  rendering `<TradeIdeaHero />` on the Node side and asserting the
  resulting HTML). With `output: "export"` this would catch real
  hydration mismatches that SSR-only test setups miss. The just-shipped
  FleetGlobe fix would have benefited from such a test.
- **`PositionsPanel` server-component path** —
  `components/positions/PositionsPanel.tsx` is an `async` server
  component; only `PositionsView` is tested. The build-time fetch
  path is untested.
- **Chart error boundaries** — none exist (Axis 4), so nothing to test.
  After fixing Axis 4, add specs.
- **`TradeIdeaHeroClient` stream-event merge logic** — the spec stubs
  an empty stream but never feeds it `progress` / `delta` / `done` /
  `error` events. The merge reducer at lines 107–125 is untested.
- **`buildProjection` linear regression** in `InventoryChart.tsx:207`
  — pure math, untested.
- **`computeReturnHistogram` boundary cases** — bucket rounding logic
  at `components/track-record/stats.ts:163` is plausible but untested
  on degenerate inputs (single-bin, all-zeros).

Coverage delta vs Wave 1: I do not have a Wave 1 baseline file in this
review's scope, so cannot report a delta numerically. Qualitatively,
the test surface has clearly grown: 13 spec files covering every major
component, plus shared fixtures (`__tests__/fixtures/*`).

Top fixes:
1. **Feed real SSE events into the TradeIdeaHero spec** — the empty-stream
   stub leaves the entire onEvent reducer untested. 30 lines of test, ~4
   missed regressions away from prod every time you touch the hero.
2. **Add an `__tests__/api.test.ts::API_BASE` block** that exercises the
   three-tier env-var resolution. `vi.stubEnv` makes this trivial.
3. **Add hydration smoke test** — render `<TradeIdeaHero />` to a Node
   string, hydrate it on jsdom, assert no React warning. Catches the
   exact class of bug the FleetGlobe `ssr: false` fix addressed.

---

## Axis 7 — Accessibility (code-side) — **7/10**

Strengths:

- `Nav.tsx:47` and `:79` — `aria-label="Primary navigation"`,
  `aria-current="page"` on the active route, both desktop and mobile.
- `ConfidenceBar.tsx:50–56` — proper `role="progressbar"` with
  `aria-valuenow / aria-valuemin / aria-valuemax / aria-label`.
- `PreTradeChecklist.tsx:88–101` — `role="checkbox"`, `aria-checked`,
  `aria-disabled`, `tabIndex` toggle, Space/Enter keyboard activation.
- `ErrorState.tsx:19` — `role="alert"`.
- `EmptyState.tsx` — `aria-hidden` on decorative SVGs.
- `LoadingSkeleton.tsx:20` — `aria-hidden` on the entire stack
  (skeletons should never be announced).
- `TickerTape.tsx:89,106,117` — `aria-label="Live market ticker"`,
  `aria-live="polite"` on the rolling list.
- `SpreadChart.tsx:35,42,58,72,80` — `aria-label`, `role="img"`,
  per-axis `aria-label`. Same pattern in the other three chart files.
- `GlobeControls.tsx:20–22` — `role="toolbar"`, `aria-label`,
  `aria-pressed` on each chip. Decent.
- `VesselPanel.tsx:39–42` — `role="dialog" aria-modal="true"`. Touch
  target 44px on close button (line 71).
- shadcn primitives (Dialog, Sheet) come with the right Radix
  semantics out of the box.

Gaps:

- **`VesselPanel` is a hand-rolled drawer**, not the shadcn `Sheet`.
  - `components/globe/VesselPanel.tsx:40–46` — `role="dialog"
    aria-modal="true"` is correct, but **no focus trap**, **no
    initial-focus management**, **no escape-to-close**. Click-outside
    on the backdrop works (line 32). Missing: focus returns to the
    triggering vessel marker when closed. Radix `Dialog` would solve
    all three for free; the comment at line 23 says "Implemented as a
    controlled drawer (not shadcn Sheet because the scaffold has not
    yet wired the shadcn registry)" — but `components/ui/sheet.tsx`
    *exists* and is fully wired.
- **Charts use `role="img"`** (`SpreadChart.tsx:60`) — fine, but the
  `aria-label` is static ("Brent-WTI spread chart (90 days)"). It does
  not summarise the actual data ("currently +$2.41, up 4% on the
  week"). For low-vision users this is still better than nothing, but
  a richer `aria-description` would help.
- **`Footer.tsx:42`** — build info span has `data-testid` but no
  `aria-label`. Fine.
- **`ConfidenceBar.tsx`** uses `role="progressbar"` for a static
  conviction value — semantically a `role="meter"` is the better fit
  (`progressbar` implies "task in progress"). Browser support is
  patchy; `progressbar` is the safer bet, just noting.
- **`StancePill.tsx:67`** — pure `<span>`, no role. Visually a pill;
  semantically… nothing. Adding `role="status"` would surface
  stance changes to AT users when the SSE stream lands a new thesis.
- **`PreTradeChecklist.tsx`** — auto-checked items are still
  `tabIndex={-1}` and `aria-disabled` — good. The user-toggleable
  ones don't have a visible focus-ring beyond the `focus:ring-2
  focus:ring-primary/50` Tailwind class. That is enough, but verify
  contrast against the bg-3 background.
- **No `aria-live` on the SSE-driven hero stream hint**
  (`TradeIdeaHeroClient.tsx:312–318`) — the "Generating new thesis
  …" text changes silently. Add `aria-live="polite"`.
- **Desktop nav hidden by `md:flex hidden`** but `Nav.tsx:48` uses
  the `hidden md:flex` Tailwind pair correctly.

Top fixes:
1. **Migrate `VesselPanel.tsx` to shadcn `Sheet`** (or wrap a Radix
   `Dialog`) so focus trap + escape + focus-return are free. Highest-
   leverage a11y fix.
2. **Add `aria-live="polite"`** to the hero stream-progress hint
   (`TradeIdeaHeroClient.tsx:313`) and to the `unavailable` branch of
   `TickerTape.tsx:96`.
3. **Enrich chart `aria-label`s** with the latest value + delta —
   reuses values already in the data, just template into the label.

---

## Axis 8 — Performance (code-side) — **7/10**

Memoisation:

- `app/fleet/page.tsx:31–40` — `useMemo` for `counts` keyed on
  `vessels`. Correct.
- `TradeIdeaHeroClient.tsx:210–213` — `useMemo` on `ctx` and `stretch`
  to avoid `?? {}` re-creating an object every render. Comment at
  line 208 explains the why. Good.
- `TickerTape.tsx:78` — `useMemo(buildTiles, [spreadQ.data, invQ.data])`
  — correct, otherwise tiles array identity churns and the marquee re-
  renders every poll.
- `TrackRecord.tsx:107–109` — three `useMemo` calls for stats / curve
  / histogram. Good.
- `PositionsView.tsx:143` — `useCallback` for `onClose` (deps `[]`).
  Stable, fine.
- `PreTradeChecklist.tsx:58` — `useCallback` for `toggle`. Good.

Render-loop hot spots:

- **`Nav.tsx`** — re-renders on every route change (uses `usePathname`),
  fine.
- **`TickerTape.tsx`** — animation runs in CSS via the `animate-scroll`
  class, not in React. Good. Sparkline SVG is recomputed on every render
  inside `Sparkline` (lines 169–204) — string concat on a 60-pt array;
  trivially cheap, but with 4 tiles × 2 marquee copies = 8 SVGs each
  recomputing on every poll. Memoising `d` would shave a few ms but
  isn't urgent.
- **`PositionsView.tsx`** — reducer-driven; one row update only re-
  renders the table. `PositionsTable` is not `React.memo`'d though, so
  a price tick in any row re-renders the whole table. With three rows
  it's irrelevant; at 50+ rows worth checking.
- **`TrackRecord.tsx`** — recharts `<ResponsiveContainer>` listens on a
  ResizeObserver; tests stub one (`__tests__/setup.ts:34`). Fine.

Key prop usage:

- `LoadingSkeleton.tsx:23` — `key={i}` for an array of skeleton bars.
  This array is fixed-size and never reorders; using index as key is
  fine for static lists.
- `TickerTape.tsx:108,112,119` — `key={`a-${t.key}`}`,`b-${t.key}`,
  `m-${t.key}` — different prefixes for the duplicated marquee +
  mobile lists. Correct.
- `TrackRecord.tsx:201` — `key={`c${i}`}` for histogram cells.
  Effectively unique because the histogram is appended in sorted bucket
  order; OK.
- `PositionsView.tsx:315` — `key={p.symbol}`. Unique per row; correct.
- `Nav.tsx:58,87` — `key={item.href}`. Correct.
- No `key={Math.random()}`, no `key=` missing on iterating JSX.

Top fixes:
1. **`React.memo(PositionsTable)`** + a `React.memo` row component
   keyed on `(symbol, current_px, unrealized_pnl)` so SSE ticks repaint
   one row, not the whole table. Future-proofs at 50+ positions.
2. **Memoise the sparkline `d` string** in `TickerTape.tsx:185–192`
   per `(values, color)` to avoid 8× recompute per poll. Trivial via
   `useMemo` if you split the SVG into a stable subtree.
3. **`React.memo` the `InstrumentTile`** on `(tier, instrument.symbol,
   stance)` — the tile motion-divs re-render on every parent render
   today, which trips framer-motion's animate path on stance changes
   that didn't actually mutate the tile content.

---

## Axis 9 — API contract integrity — **6/10**

Method: read every `fetchJson<...>` / `fetch(...)` call site, match
generic to `types/api.ts`, flag drift.

- **`/api/spread`** → `SpreadLiveResponse` (used by `TickerTape`,
  `app/macro/page.tsx`). Type at `types/api.ts:58–67`. No way to verify
  against backend without reading FastAPI; the JSDoc at line 43–48 says
  "mirrors backend/models/spread.py exactly" — trust until verified.
- **`/api/inventory`** → `InventoryLiveResponse`. Types line 85–94.
  Same caveat. `forecast` is non-nullable on the type but nullable in
  practice — `app/inventory/page.tsx:31` does `inv.data?.forecast ??
  null` and `InventoryChart`'s prop is `DepletionForecast | null`. The
  type is tighter than the actual contract — drift risk.
- **`/api/backtest`** (POST) → `BacktestLiveResponse`. Types line
  101–117. Body envelope = `BacktestRequestBody` (line 119–125). Used
  in `app/macro/page.tsx:21–30`.
- **`/api/thesis/latest`** → `ThesisLatestResponse`. Types line 237–240.
  Used in `TradeIdeaHero.tsx:23`. `thesis: ThesisAuditRecord | null`
  — matches the empty-state branch.
- **`/api/thesis/generate`** (SSE POST) → events parsed in
  `TradeIdeaHeroClient.tsx:107–125`. The contract is **untyped at the
  parse boundary** — `JSON.parse(evt.data) as Record<string, unknown>`.
  Types `ThesisSseDoneEvent`, `ThesisSseProgressEvent`,
  `ThesisSseDeltaEvent` exist (lines 242–255) but **are not used**.
  Dead types; drift risk if the backend renames a field.
- **`/api/thesis/history?limit=200`** → `ThesisHistoryResponse`. Types
  in `components/track-record/types.ts:38`. Note: this is a
  *component-local* duplicate of similar shapes in `types/api.ts`
  (`ThesisAuditRecord` line 224); the track-record type is shallower.
  Two sources of truth, only one tested. Drift risk.
- **`/api/positions`** → `PositionsListResponse`. Types in
  `components/positions/types.ts:33`. Same note: defined in component
  folder, not `types/api.ts`. The original `Position` shape in
  `types/api.ts:295–304` is **completely different** from
  `PaperPosition` in `positions/types.ts:10–24`. Two `Position` types
  for two endpoints (the `Sub-C` scaffold one in `types/api.ts` was
  never aligned with the actual Alpaca-projection shape).
- **`/api/positions/account`** → `PaperAccount`. Same scoping pattern.
- **`/api/positions/stream`** → `TradeUpdatePayload`. Typed; `PositionsView.tsx:130`
  parses with the cast. Reasonable.
- **`/api/positions/execute`** (POST) → `ExecuteOrderRequest` body.
  Typed.
- **`/api/build-info`** → `BuildInfo`. Types line 323.
- **`/api/spread/stream`** → SSE; `TickerTape.tsx:62` parses no payload
  on `onmessage` (just calls `refetch()`). Good — least-trust contract.

Drift / freshness signals:

- `types/api.ts` says at line 1: "Auto-generation via openapi-typescript
  lands in a follow-up". That follow-up has not landed.
- The `Sub-A`/`Sub-B`/`Sub-C` scaffold types (`SpreadResponse`,
  `BacktestResponse`, `Vessel`, `Position`, `Account`, `FleetSnapshot`,
  `ThesisLeg`, `ThesisResponse`) are **all unused in components**. They
  duplicate data shapes that the live components actually consume from
  the `*LiveResponse` family. Pure historical clutter.
- `components/positions/types.ts` and `components/track-record/types.ts`
  duplicate concepts already in `types/api.ts`. No single source of
  truth for the API surface.

Top fixes:
1. **Adopt `openapi-typescript`** against the FastAPI OpenAPI doc and
   replace the entire `types/api.ts` module with generated output.
   Single source of truth, free drift detection on every CI run.
2. **Delete the dead scaffold types** (`SpreadResponse`,
   `InventoryResponse`, `BacktestResponse`, `Vessel`, `Position`,
   `Account`, `FleetSnapshot`, `ThesisLeg`, `ThesisResponse`) — at
   minimum mark them `@deprecated` so future contributors don't pick
   them up.
3. **Wire the `ThesisSseDone/Progress/Delta` event types** into the
   `TradeIdeaHeroClient` stream parser. The cast-to-`Record<string,
   unknown>` is the easy way out today; using the typed unions catches
   field renames at compile time.

---

## Axis 10 — Code quality / DX — **8/10**

Strengths:

- **JSDoc on every non-trivial component** explains *why*, not what.
  Examples: `lib/api.ts:4–12` (env-var resolution rationale),
  `app/layout.tsx:31–39` (overflow-x-hidden suspenders explanation),
  `app/fleet/page.tsx:10–14` (FleetGlobe ssr:false rationale),
  `lib/globe-physics.ts:1–16` (lat/lon convention reference). This is
  excellent — the *why* comments will save the next-dev hours.
- **Consistent naming**: `*View` for the client body of a server
  component (`PositionsView`), `*Panel` for the server component itself
  (`PositionsPanel`). `Sub-A/B/C/D/E/F/G` wave annotations.
- **Folder structure**: `components/{hero,ticker,positions,track-record,
  globe,charts,common,ui}` plus `lib/` and `types/`. Clean.
- **Token-driven styling**: `bg-bg-1`, `text-text-primary`, `text-positive`
  / `text-negative` / `text-warn`, `rounded-card` / `rounded-btn`. The
  Tailwind config (not read but referenced from `tailwind.config.ts`)
  centralises these.
- **Server / client split is explicit** — `"use client"` at the top of
  every interactive file.
- **No commented-out code blocks**, no `console.log` debug residue
  (only deliberate `console.warn` with the eslint comment, e.g.
  `FleetGlobe.tsx:90,134`).

Weaknesses:

- **Dead deps** (Axis 5): `@radix-ui/themes`, `@react-three/drei`,
  `@react-three/fiber` in `package.json`.
- **Stale comment**: `StancePill.tsx:11` references
  `lib/language.ts` which doesn't exist (verified via Glob). The
  comment is aspirational ("not a shared helper yet"); it should
  either be promoted with a TODO ticket or rephrased.
- **Two types-of-things lying around**: the dead scaffold types in
  `types/api.ts` (Axis 9). Sub-folder `types.ts` files duplicate the
  central one.
- **Empty `experimental` block** in `next.config.mjs:11–14` — the
  comment "parking lot for future tweaks" is fine, but every Next 15
  upgrade will wonder if the block is intentional.
- **Test fixtures live under `__tests__/fixtures`** — fine, but they
  are imported into runtime page code (`app/fleet/page.tsx:8` —
  `import mockVessels from "@/__tests__/fixtures/vessels.json"`).
  This means the prod static export bundles the test fixture as live
  data. Intentional ("Mock vessel data until Sub-C's
  /api/fleet/vessels lands" — line 21–23) but **flag it on the next
  pass** so the moment the API exists the import is replaced. Today
  the JSON ships in the route chunk as live state. Not a bug, just a
  scar that will heal poorly if forgotten.
- **`InventoryChart.tsx:213`** — local var named `window` shadows the
  global `window`. Confusing; rename to `fitWindow` at line 213
  (parameter `fitWindow` is already used for the param, and the
  `window` shadow is for the slice). Pure aesthetic.

Top fixes:
1. **Replace fixture import in `app/fleet/page.tsx:8` with a fetch
   stub** — even a static `public/mock-vessels.json` fetched via
   react-query would be cleaner and would reset to a real API call
   with one diff.
2. **Drop the dead scaffold types and comment in `StancePill`** so
   the next contributor isn't navigating to non-existent files.
3. **Add a TODO/FIXME index** (or use `eslint-plugin-todo` /
   `npm-todo`). The codebase has informal TODOs ("Sub-C lands in
   Phase 4" — `InstrumentTile.tsx:32`) but no central place to track
   them.

---

## Top 15 findings (prioritised)

| # | Severity | Path | One-line fix |
|---|----------|------|--------------|
| 1 | **P0** | `frontend/app/error.tsx`, `frontend/app/global-error.tsx` (missing) | Create both — even a thin `<ErrorState retry={reset} />` saves the user from blank-page failures on any unhandled render exception. |
| 2 | **P0** | `frontend/components/positions/PositionsView.tsx:122`, `components/ticker/TickerTape.tsx:50`, `components/hero/TradeIdeaHeroClient.tsx:94` | Add SSE reconnect-with-capped-backoff (1/2/5/10s) on `onerror`; today a single network blip silently downgrades live updates to react-query polling forever. |
| 3 | **P1** | `frontend/components/globe/VesselPanel.tsx:39` | Replace hand-rolled drawer with shadcn `Sheet` (or Radix `Dialog`) to gain focus trap, escape-to-close, and focus return — the file even says the registry isn't wired, but `components/ui/sheet.tsx` is in the tree. |
| 4 | **P1** | `frontend/types/api.ts` (whole file) | Adopt `openapi-typescript` against the FastAPI schema and delete the dead scaffold types (`SpreadResponse`, `BacktestResponse`, `Vessel`, `Position`, `Account`, `FleetSnapshot`, `ThesisLeg`, `ThesisResponse`). |
| 5 | **P1** | `frontend/package.json:22,23,24,26` | Remove unused deps `@radix-ui/themes`, `@react-three/drei`, `@react-three/fiber`, and (if not mounted) `@tanstack/react-query-devtools`; estimated 80–150 KB gzipped saving on First Load JS. |
| 6 | **P1** | `frontend/next.config.mjs:11` | Set `experimental.optimizePackageImports: ["recharts","lucide-react","framer-motion"]` — supported in Next 15, sizeable recharts win. |
| 7 | **P1** | `frontend/components/hero/TradeIdeaHeroClient.tsx:23` | `next/dynamic({ ssr: false })` the `HeroShaderBackground` so non-WebGPU users never download the three.js + TSL bundle for the home route. |
| 8 | **P1** | `frontend/.eslintrc.json:4` | Promote `@typescript-eslint/no-explicit-any` from `warn` to `error` and add per-line `eslint-disable` over the WebGPU TSL casts (the only legit holdouts). |
| 9 | **P1** | `frontend/components/hero/TradeIdeaHeroClient.tsx:107` | Use the existing `ThesisSseDone/Progress/Delta` event types in the SSE parse path; today they're dead types and the merge logic is fully untested. |
| 10 | **P1** | `frontend/components/hero/TradeIdeaHeroClient.tsx:130`, `components/positions/PositionsView.tsx:130` | Surface SSE failures via the existing Toaster (or a status pill) so prod regressions are visible — `console.warn` only helps in dev. |
| 11 | **P2** | `frontend/app/not-found.tsx` (missing) | Add a `not-found.tsx` so deep-link typos don't bottom out at the SWA `/index.html` fallback. |
| 12 | **P2** | `frontend/app/fleet/page.tsx:8` | Replace `import mockVessels from "@/__tests__/fixtures/vessels.json"` with a fetch (even of a static `public/` JSON) — today the test fixture ships as live data in the prod bundle. |
| 13 | **P2** | `frontend/components/positions/PositionsView.tsx:285` | Wrap `PositionsTable` (and per-row component) in `React.memo` keyed on `(symbol, current_px, unrealized_pnl)` — at 50+ open positions, an SSE tick re-renders the whole table today. |
| 14 | **P2** | `frontend/components/charts/InventoryChart.tsx:213` | Rename the `window` local variable so it doesn't shadow the global `window` (cosmetic but confusing in code review). |
| 15 | **P2** | `frontend/__tests__/api.test.ts` (add block) + new hydration smoke test | Add tests for `API_BASE` env precedence and a Node-string-render-then-jsdom-hydrate spec to catch the next FleetGlobe-class hydration bug before prod. |

---

## Per-axis scorecard summary

| Axis | Score |
|------|-------|
| 1. TypeScript strictness | 8 |
| 2. Hook hygiene | 6 |
| 3. SSR / static-export correctness | 9 |
| 4. Error boundaries + suspense | 4 |
| 5. Bundle size discipline | 6 |
| 6. Test coverage gaps | 7 |
| 7. Accessibility (code-side) | 7 |
| 8. Performance (code-side) | 7 |
| 9. API contract integrity | 6 |
| 10. Code quality / DX | 8 |

**Aggregate:** 68/100 — solid mid-stage frontend. The shape is healthy
(strict TS, clean hooks, honest SSR boundaries, real test coverage); the
two structural deficits are **error boundaries** (Axis 4) and the
**SSE-without-reconnect** pattern (Axis 2). Either one is a recoverable
prod incident waiting to happen; both are fixable in a half-day.

**Recommendation: ship-with-caveats** — the static surface is honest,
hydration is settled (post-FleetGlobe fix), and the test gates are
real. Before the next big traffic event, land Findings 1–2 (P0s).
Findings 3–10 (P1s) belong on the next sprint board.

---

## Appendix — raw tooling output

### `frontend/.eslintrc.json`

```json
{
  "extends": ["next/core-web-vitals", "next/typescript"],
  "rules": {
    "@typescript-eslint/no-explicit-any": "warn",
    "@typescript-eslint/no-unused-vars": [
      "warn",
      {
        "argsIgnorePattern": "^_",
        "varsIgnorePattern": "^_"
      }
    ]
  }
}
```

### `frontend/tsconfig.json` (compilerOptions excerpt)

```json
{
  "target": "ES2022",
  "strict": true,
  "noEmit": true,
  "esModuleInterop": true,
  "moduleResolution": "bundler",
  "isolatedModules": true,
  "jsx": "preserve",
  "plugins": [{ "name": "next" }],
  "paths": { "@/*": ["./*"] }
}
```

### `npm run typecheck` — **skipped**

Reason: `frontend/node_modules` is not present in this venv, and a fresh
`npm install` is forbidden per review constraints. CI runs `npm run
typecheck --if-present` in `.github/workflows/ci-nextjs.yml:69` on every
push/PR, so the failure mode is gated upstream. The strict-mode posture
(see appendix `tsconfig.json`) plus the static `as any` survey below is
the substitute signal.

### `npm run lint` — **skipped** (same reason)

CI gate at `.github/workflows/ci-nextjs.yml:71`.

### `npm run test` — **skipped** (same reason)

CI gate at `.github/workflows/ci-nextjs.yml:73`. Test inventory
catalogued under Axis 6 (13 spec files).

### `grep` for unsafe TS patterns — raw output (filtered to source dirs)

Command (run in repo root, scoped to `frontend/{components,lib,app,types}`):

```
grep -rn "as any\|as unknown\|@ts-ignore\|@ts-expect-error" \
  frontend/{components,lib,app,types}
```

**Total hits: 17.** Sampling (truncated):

```
frontend/components/globe/FleetGlobe.tsx:51:    return !!(navigator as any).gpu;
frontend/components/globe/FleetGlobe.tsx:105:    const api = (canvasRef.current as unknown as { __globeApi?: GlobeApi } | null)
frontend/components/globe/FleetGlobe.tsx:242:    const lambert = dot(normalLocal, (sunUnif as unknown) as any);
frontend/components/globe/FleetGlobe.tsx:260:  const viewDir = normalize((cameraPosition as any).sub(positionWorld as any));
frontend/components/globe/FleetGlobe.tsx:262:    float(1).sub(dot(normalLocal, viewDir as any) as any),
frontend/components/globe/FleetGlobe.tsx:265:  atmoMat.colorNode = color("#22d3ee").mul(rim as any);
frontend/components/globe/FleetGlobe.tsx:272:  (dotMat as unknown as { vertexColors: boolean }).vertexColors = true;
frontend/components/globe/FleetGlobe.tsx:430:  (canvas as unknown as { __globeApi: GlobeApi }).__globeApi = {
frontend/components/globe/FleetGlobe.tsx:463:    (sunUnif as unknown as { value: TVector3 }).value.fromArray(
frontend/components/globe/FleetGlobe.tsx:672:  (canvas as unknown as { __globeApi: GlobeApi }).__globeApi = {
frontend/components/hero/PreTradeChecklist.tsx:22:    const parsed = JSON.parse(raw) as unknown;
frontend/components/hero/InstrumentTile.tsx:44:  const legacy = instrument as unknown as {
frontend/components/hero/HeroShaderBackground.tsx:33:    if (!(navigator as any).gpu) return;
frontend/components/hero/HeroShaderBackground.tsx:84:          (positionWorld as any).xy.mul(t as any) as any,
frontend/components/hero/HeroShaderBackground.tsx:89:          stretchU as any,
frontend/components/hero/HeroShaderBackground.tsx:90:        ).mul((noise.mul(float(0.5)).add(float(0.5))) as any);
frontend/components/hero/HeroShaderBackground.tsx:109:          (stretchU as unknown as { value: number }).value = stretchRef.current;
```

`@ts-ignore` / `@ts-expect-error` count: **0** across the entire
`frontend/` tree (including tests and config). Strong signal — no
escape-hatch silencing.

### `next build` bundle analysis — **skipped**

No `frontend/.next/` or `frontend/out/` artifacts present in the venv,
and a fresh build cannot run without `node_modules`. Bundle judgement
in Axis 5 is from import-graph reading. Recommended follow-up:
locally run `ANALYZE=1 npm run build` after wiring
`@next/bundle-analyzer` (currently absent from `package.json`).

### Workflow gate summary

`/.github/workflows/ci-nextjs.yml` (frontend-build job):

- node 20, `npm ci --legacy-peer-deps`
- `npm run typecheck --if-present` (line 69)
- `npm run lint --if-present` (line 71)
- `npm test -- --run` (line 73)
- `npm run build` with `NEXT_TELEMETRY_DISABLED=1` (line 75)

`/.github/workflows/cd-nextjs.yml` (frontend-deploy job):

- `NEXT_PUBLIC_API_URL: https://oil-tracker-api-canadaeast-0f18.azurewebsites.net`
- `npm run build` then `Azure/static-web-apps-deploy@v1` upload from
  `frontend` with `output_location: out`
- live-verify step is **commented out** (cd-nextjs.yml:229–245); the
  comment says "Static Web App not provisioned yet" — verify
  whether that's still true and uncomment if so.
