# Wave 5 backlog

Captured during the Wave 4 wrap-up. Each item is a candidate for a
dedicated Wave 5 session. Sized loosely; sequence matters less than
resource availability.

## 1. AISStream live data swap-in (~1 day)

`/api/fleet/snapshot` + `/api/fleet/vessels` SSE currently warm a
producer task on first hit but the production Azure App Service
container does not always hold the websocket open between requests.
Switch the producer to a background asyncio task on app startup and
add a simple liveness ping so the React `<FleetGlobe>` shows a
"refreshing every Ns" status when the stream is up.

Files: `backend/services/fleet_service.py`, `backend/main.py`
(startup hook), `frontend/components/globe/FleetGlobe.tsx`.

## 2. Streamlit teardown after 48h stable on React (~30 min)

Earliest: 2026-04-27 04:00 UTC (48h after `ddc4f8f` deploy on
2026-04-25 04:11 UTC). Once the React stack stays green for 48h,
delete the Streamlit Web App + plan:

```bash
az webapp delete -g oil-price-tracker -n oil-tracker-app-canadaeast-4474 --keep-empty-plan
az appservice plan delete -g oil-price-tracker -n oil-tracker-canadaeast-plan --yes
```

Also remove the Streamlit ping from `keep-warm.yml` (already non-fatal
but no longer needed) and delete `app.py` + `tests/e2e/test_*.py` that
target the Streamlit UI.

## 3. Custom domain on the Static Web App (~2 hours)

The SWA URL `delightful-pebble-00d8eb30f.7.azurestaticapps.net` is fine
for demos but the brand polish lands on a custom domain. Buy a domain,
configure CNAME on the Static Web App, update OIDC AAD redirect-URIs.
Update `keep-warm.yml`, `cd-nextjs.yml` SHA-verify URL, and frontend
metadata (`app/layout.tsx ‣ Metadata.url`).

## 4. Stripe paywall stub for premium tier (~1 day)

Backend: a `/api/billing/checkout` POST that creates a Stripe Checkout
Session, plus a webhook handler `/api/billing/webhook` that updates a
user-tier table. Frontend: a "Premium" badge on the hero card that
gates regenerate-thesis past the 3-per-day free quota. All behind a
`STRIPE_ENABLED=false` flag until ready to ship.

Files: `backend/routers/billing.py`, `frontend/components/billing/`,
new `data/user_tiers.jsonl`.

## 5. Slack/Discord webhook alerting (~half day)

When a new thesis flips stance vs the prior session, fire a webhook
with the headline + plain-English summary + a permalink. Store
webhook URLs as App Service secrets. Mute by default; trader opts in
per-symbol. Useful for desk traders who want to be pinged on state
changes without having the page open.

Files: `backend/services/alerting.py`, env vars `SLACK_WEBHOOK_URL`,
`DISCORD_WEBHOOK_URL`.

## 6. Foundry GPT-5 migration (already started)

Provision Foundry hub + project, deploy `gpt-5` and `gpt-5-mini`,
swap `trade_thesis.py` to use the agents SDK behind a `USE_FOUNDRY`
feature flag. Agent tools to expose: `get_current_spread_context`,
`run_cointegration_test`, `query_cftc_positioning`,
`run_backtest_on_window`, code-interpreter for ad-hoc scenario math.
Design doc: `docs/designs/foundry-migration.md`. Blocked on Foundry
quota approval per the earlier autonomous-attempt comment.

## 7. Major-bump dependency upgrade slot (~half day)

Held PRs:
- numpy ≥ 2.4.4 (#10)
- pandas ≥ 3.0.2 (#9)
- scikit-learn ≥ 1.8.0 (#7)
- docker python:3.14-slim (#6)
- vite 5 → 7/8 + esbuild 0.21 → 0.27 (#12 closed; will recreate)

Run the full pytest + frontend test suite against each pin, document
breakage, fix or close. Coordinate the vite + vitest + @types/node
bumps in a single dedicated session.

## 8. P1 product wave — auth + execute UI

Tasks #87–#92 from the master list:
- P1.2 Alpaca OAuth + SDK wrapper (per-user creds vs the single shared
  paper account)
- P1.3 Execute-this-trade UI (right now the button is disabled)
- P1.4 Live positions + P&L panel (already shipped via Phase 1; needs
  per-user filtering once auth lands)
- P1.5 Signal track record + public route
- P1.6 Onboarding flow
- P1.7 Notifications — in-app + email
- P1.8 Mobile + UX polish v3
- P1.9 Regulatory pages

Wave 5 is the right time to tackle the auth slice (P1.1 is already
merged but P1.2+ blocks).
