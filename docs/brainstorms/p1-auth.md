# P1.1 — Authentication + User Store (Brainstorm)

> **Status:** ARCHIVED (2026-04-22 00:55Z). The Clerk pivot was
> paused before execution when Aidan reprioritised: **UI polish
> first, then simplified single-user Alpaca (static env-var API
> keys, not OAuth)**. The shipped P1.1 auth scaffolding (`User`,
> `UserStore`, `current_user()`, `@requires_auth`, sign-in button
> placeholder) stays in place as infrastructure — the product is
> now "Aidan's personal oil research desk", so a multi-user IdP
> (Google, Clerk, or otherwise) is not on the critical path. If we
> ever return to multi-user, the Clerk delta at the bottom of this
> doc + the parallel delta in the design spec + plan addendum are
> the warm-start.

> **Prior status (historical):** RESOLVED 2026-04-22 with Streamlit
> native `st.login()` + Google OIDC — shipped in P1.1 (SHAs
> `65f632f..8245172` merged as `3f39ff4`). Aidan dropped Google and
> picked Clerk, then before Clerk was built, dropped the multi-user
> premise entirely.

## Clerk pivot (2026-04-22)

Aidan's directive: drop Google. Use Clerk.

**Why the pivot is cheap:** the P1.1 architecture split the IdP
(`auth/session.py::_user_from_streamlit_session`) from the rest of
the auth stack (user store, decorator, widgets, mock-auth seam).
Every provider-agnostic surface stays — only the "how does a user
prove who they are" branch swaps.

**Clerk integration shape** (lowest-friction option surveyed):

1. **Sign-in button is a link**, not a `st.button()` click-handler.
   The link target is Clerk's hosted sign-in page:
   `https://<clerk-subdomain>.clerk.accounts.dev/sign-in?redirect_url=<app>`.
   Clerk owns the entire sign-in UX (email+password, magic link,
   GitHub). No custom UI we maintain.

2. **Return leg** — Clerk redirects to our app with the session JWT
   appended as a query parameter (the `__clerk_db_jwt` handshake
   pattern for cross-origin hosts that don't embed Clerk's frontend
   SDK). We read the JWT from `st.query_params`, verify the signature
   against Clerk's JWKS (`https://<subdomain>.clerk.accounts.dev/.well-known/jwks.json`),
   and extract the standard claims (`sub`, `email`, `name`,
   `picture_url`).

3. **Session persistence** — after a successful verify, we persist
   the validated claims into `st.session_state["_auth_user"]` AND
   into a Streamlit signed cookie (native `st.context.cookies` in
   v1.42, or `streamlit-cookies-controller` as a fallback). The
   Clerk JWT itself is not stored — only the verified claims are.

4. **Logout** — link to Clerk's hosted sign-out URL. Local cleanup
   (`clear_cached_user()`) happens on the redirect back.

**Env var change:** drop `GOOGLE_OAUTH_CLIENT_ID` /
`GOOGLE_OAUTH_CLIENT_SECRET`. Add:
- `CLERK_PUBLISHABLE_KEY` — prefixed `pk_live_` or `pk_test_`; its
  tail encodes the Clerk subdomain.
- `CLERK_SECRET_KEY` — prefixed `sk_live_` or `sk_test_`; used for
  backend-API calls (e.g. user lookup by id). Not needed for JWT
  verify; needed for later features like "disable user".
- `CLERK_JWKS_URL` — optional override; we derive this from
  `CLERK_PUBLISHABLE_KEY` by default.

**Same guardrails hold.** `STREAMLIT_ENV=prod` still gates the
`MOCK_AUTH_USER` bypass. `boot_check()` still validates required
env vars. User store shape is unchanged (Clerk's `sub` is stable —
drop-in replacement for Google's `sub`).

**Reversibility.** If Clerk goes sideways, swap to Auth0 / Supabase
Auth / Azure AD B2C by rewriting only `auth/clerk.py` (and renaming
to `auth/<provider>.py`). The session.py seam stays.

## The user problem, restated

The macro-oil-terminal is about to become a trading site. Phase-1 features
1.2 (Alpaca OAuth), 1.3 (Execute-this-trade), 1.4 (Live positions), 1.5
(Track record), 1.6 (Onboarding), 1.7 (Notifications) all assume a
*known user* with a persistent identity across visits. P1.1 is the ground
that every one of those features stands on. If we get it wrong, we either
eat a rewrite when P1.2 shows up or we ship broker tokens in plaintext
session state. Either is unacceptable.

What P1.1 must produce:

1. **A signed-in user concept** — somewhere between `st.session_state`
   and the database, `st.user.email` returns a trusted email and a
   stable user id.
2. **A user record** — persisted across sessions, with slots for the
   broker-token references P1.2 will write, and the notification
   preferences P1.7 will write.
3. **A gate** — a decorator or a guard at render time that says "you
   can see this widget / execute this action only if signed in". Today's
   UX (public research, public hero thesis, public track record) stays.
4. **A session that survives refresh** — today `st.session_state` is
   per-websocket and lost on reload. Login has to stick.
5. **A testable seam** — Playwright and pytest need to execute
   "signed-in-as-Aidan" paths without real OAuth round-trips.

What P1.1 is *not*:

- The Alpaca OAuth flow (that's P1.2).
- Stripe / paywalls (Phase 2+).
- Team-based permissions or multi-tenancy (hobby scale — one user, one
  account for now).

## Why this matters now

Hero-thesis landed yesterday. The instrument tiles surface a Paper / ETF /
Futures choice, the checklist surfaces pre-trade tickables, and the broker
search-link row exists purely because we *don't* have auth-plus-broker-
integration. Every follow-on Phase-1 feature assumes we do. P1.1 turns
the page from "hobby dashboard with a strong thesis" to "a product you
can log into", which is the pre-req for *every* execution feature.

## Alternatives considered

### A. Streamlit native `st.login()` + Google OIDC (v1.42+)

Streamlit shipped `st.login()` and `st.user` in February 2025 (v1.42).
Configure an OIDC provider in `.streamlit/secrets.toml`, drop
`st.login("google")` into the app, and Streamlit handles the
authorization-code flow, the signed cookie, and `st.user.is_logged_in`.
It's built on Authlib under the hood — every standards-compliant OIDC
IdP works. Google OIDC is free, ubiquitous, and every trader already
has an account.

**Wins:** Zero new vendors. Zero monthly cost. Signed-cookie session
persistence out of the box. Drop-in API. Reversible — swap Google for
Clerk or Auth0 by editing `secrets.toml`.

**Loses:** Tied to Streamlit's auth lifecycle (if they break it, we
have to follow the migration). No built-in admin UI for managing
users — if we need to disable a user, we do it in our user store,
not in an IdP console.

### B. Clerk as the OIDC IdP behind `st.login()`

Same Streamlit-native surface as A, but point the OIDC provider config
at Clerk. Gives us Clerk's user-management UI, MFA, email
verification, and a React widget we don't need.

**Wins:** Nicer admin UI (see, disable, impersonate users in Clerk's
dashboard). Built-in MFA if we ever need it.

**Loses:** Adds a vendor and a bill. Clerk's free tier is 10k MAU
(fine today), but "custom OIDC provider" where Clerk *relays* to
Alpaca is Pro+. That feature is also not useful to us — Alpaca is
OAuth 2.0, not OIDC, so it doesn't federate through any IdP. Clerk's
React widget is unused in a Streamlit app. We'd be paying for features
we don't consume.

### C. Supabase Auth + Supabase Postgres as the user store

Supabase's Auth + Postgres combo on the free tier gives us 50k MAU and
a real relational database. Python SDK (`supabase-py`) is maintained.

**Wins:** One vendor for both auth and user store. Postgres is nicer
than Table Storage if we ever grow to relational queries (e.g., P1.5
track-record stats joined against user preferences). Generous free
tier.

**Loses:** Another region / another latency hop. Adds a vendor.
Supabase Auth isn't wired into `st.login()` natively — we'd go back
to `streamlit-oauth` or manual flow, which is more code than native
`st.login()` with Google OIDC. Arbitrary OIDC/SAML providers on
Supabase are Pro+ anyway, so we don't unlock federated sign-in
either.

### D. Azure AD B2C + App Service Easy Auth (reverse-proxy model)

Delegate auth to the App Service platform via Easy Auth — user is
authenticated *before* the request hits Streamlit. Read
`X-MS-CLIENT-PRINCIPAL` header for identity.

**Wins:** Auth is enforced at the infrastructure layer — impossible
to forget a decorator. Built into Azure, no extra service.

**Loses:** Streamlit websocket + Easy Auth has known gotchas
(`X-Forwarded-*` handling, cookie domain mismatch). Also: the whole
site gets auth-walled, which kills the public-research surface that
drives signups. Binary all-on / all-off doesn't match the "public
research + gated execution" UX we want.

### E. Roll our own

Build an OAuth2 authorization-code flow with Authlib + a custom cookie
layer. **Rejected** — re-implementing the primitive that `st.login()`
already wraps for us.

## Decision

**Alternative A — Streamlit native `st.login()` + Google OIDC.**

Rationale:

- *Reversibility* — swap to Clerk / Auth0 / Microsoft / GitHub by
  editing `secrets.toml`. No code changes.
- *Cost* — £0/mo. Google OIDC is free, Streamlit `st.login()` ships with
  the framework we already pay for (nothing).
- *Friction for users* — "Sign in with Google" matches 2026 baseline
  expectations. Traders have Gmail. No "create an account, verify your
  email, choose a password" funnel.
- *Friction for us* — `st.login("google")` and `st.user.email`. That's
  the code.
- *Skills-match* — we already speak Authlib under the hood.

Clerk is the fallback if we outgrow the native primitive (MFA,
impersonation, team workspaces). Supabase is the fallback if we outgrow
Table Storage and want Postgres-backed joins.

## User-store alternatives considered

Separate decision from the IdP: *where does the user record live?*

### a. Azure Table Storage (chosen)

Flat key-value. Partition by region (single `users` partition today),
row key = Google `sub` (stable across email changes). ~£0.05/mo for our
volume. Already on Azure. No new resource provider. Python SDK
(`azure-data-tables`) is stable.

### b. Azure Cosmos DB

Overkill. ~£25/mo minimum. Schema-free like Table Storage but adds
query-language overhead we don't need. Saves for a later migration if
P1.5 track record needs cross-user aggregations.

### c. Supabase Postgres

Already covered under IdP alt C — rejected with C.

### d. SQLite on App Service

App Service Linux containers have ephemeral filesystems. SQLite would
lose all state on every redeploy. **Rejected.**

### e. JSON file in a blob

Single-writer bottleneck under concurrent logins. **Rejected.**

**Chosen: Azure Table Storage**, one `users` table with a minimal
schema:

```
PartitionKey: "users"
RowKey: <google_sub>        # stable Google subject identifier
email: str
name: str
picture_url: str | None
created_at: ISO-8601 UTC
updated_at: ISO-8601 UTC
alpaca_refresh_token_ref: str | None   # Key Vault secret name, filled by P1.2
alpaca_mode: "paper" | "live" | None   # filled by P1.2
notification_prefs_json: str           # JSON blob, filled by P1.7
onboarding_completed_at: ISO-8601 UTC | None   # filled by P1.6
```

Encryption-at-rest is provided by Azure. No PII beyond email and name
in this table — broker tokens go through Key Vault, never this store.

## Public-vs-gated split

Two viable shapes:

1. **Public research + gated execution** (our default): the hero
   thesis, tabs 1–3, and the track-record route stay public. Login is
   required only for "Execute this trade", the positions panel,
   notification management, and onboarding.
2. **Gate the whole site**: anyone who hits the URL sees a login wall.

We pick (1). Reasoning: the research view is the content that drives
signups. Gating it kills the acquisition funnel. Compliance-wise, the
research content is already captioned "not investment advice" — making
it public doesn't expose us more than it does today.

Implementation: an `@requires_auth` decorator on render functions that
touch broker APIs or user preferences; bare `st.login(...)` sign-in /
sign-out in the header for everyone.

## Testing seam

Two mocking levels:

- **Unit tests** (pytest): `auth.get_current_user()` returns a
  `User` dataclass. Monkey-patch it to return a fake user. Tests for
  the user store itself use `azure-data-tables`' in-memory fake (or a
  thin wrapper we can stub).
- **E2E tests** (Playwright): `MOCK_AUTH_USER=aidan@youbiquity.com`
  env var is read at app boot. If set AND `STREAMLIT_ENV != "prod"`
  (we add this env to App Service settings), the app skips real OAuth
  and injects the mocked user into the session. Guard ensures you
  can't accidentally bypass auth in prod.

## Assumptions

1. **Streamlit ≥ 1.42 is on our runtime.** `requirements.txt` pins
   `streamlit>=1.28.0` today; we'll bump to `>=1.42.0`.
2. **Google OIDC is acceptable.** We're assuming our users — oil-desk
   traders — are happy to sign in with Google. If any of our target
   users are on corporate Outlook-only tenants that block Google OAuth,
   we'd need Microsoft OIDC as a second button. (Flagged as
   open-question 1 below.)
3. **One user = one Alpaca account.** No "team trading" semantics.
4. **The `cookie_secret` is a long-lived secret** stored in Key Vault
   and injected via App Service app setting. Rotation on compromise
   only, not scheduled.
5. **App Service Easy Auth stays OFF.** We do auth in-app, not at the
   platform layer.

## Unknowns / open questions for Aidan

**Status (2026-04-22): RESOLVED.** All six adopt the proposed default.
Design spec + plan updated.

1. **IdP choice — Google only, or Google + Microsoft?** Google covers
   consumer + most GSuite-using desks. Microsoft covers Outlook-only
   corporate desks. Adding a second provider is ~10 lines in
   `secrets.toml`, but requires a second OAuth app registration.
   **Proposed default: Google only**, add Microsoft as a P2 item if a
   user asks.

2. **User-store region — which region for the Table Storage account?**
   App Service is `canadaeast` now. Table Storage should co-locate
   for latency (~5ms vs ~60ms cross-region). **Proposed default:
   canadaeast**, same RG (`oil-price-tracker`) as everything else.

3. **New-user creation trigger — on first login, or explicit
   "Sign up" step?** On-first-login is zero-friction. An explicit
   signup step lets us collect Terms-of-Service acceptance and a
   portfolio-size number up-front. **Proposed default: on first login
   with an implicit ToS-accept** (the login button text reads "Sign in
   with Google — by continuing you accept our [Terms] and [Risk
   Disclosure]"). P1.6 onboarding wizard collects the portfolio size
   number on first app-load after login. This keeps P1.1 small.

4. **OAuth consent screen branding.** Google requires an app name + a
   support-email on the OAuth consent screen users see. **Proposed
   default: app name = "Macro Oil Terminal", support email =
   aidan.marshall@youbiquity.com**. We'll also need a logo (512x512
   PNG) for the consent screen — falls back to a generic Google
   placeholder if we skip it.

5. **Cookie-secret rotation policy.** Rotate on compromise only
   (simplest), or every 90 days (defence-in-depth)? **Proposed default:
   on compromise only.** Scheduled rotation is nice but logs every
   user out — 1k MAU experience degradation for little gain.

6. **Sign-out UX.** Where does the sign-out link live? **Proposed
   default: a small "Signed in as aidan@…" caption in the header,
   with a "Sign out" link next to it.** Rendered inside the existing
   hero-band container so it doesn't add a new layout row.

## "Waiting on Aidan" signup items

Once Aidan greenlights the defaults, he (or we, if we can do it on
his behalf) needs to:

1. **Create a Google Cloud project** (or reuse an existing Youbiquity
   one) and add an OAuth 2.0 Client ID.
   - URL: https://console.cloud.google.com/apis/credentials
   - Application type: Web application
   - Authorised redirect URI:
     `https://oil-tracker-app-canadaeast-4474.azurewebsites.net/oauth2callback`
     (and `http://localhost:8501/oauth2callback` for dev)
   - Returns: `client_id` + `client_secret`.
2. **Not required for P1.1**: Clerk, Supabase, SendGrid, Alpaca
   signups. Those come in P1.2 / P1.7.

Everything else is code.

## Residual default

Anything else that surfaces and isn't covered here: apply the
"most-conservative, minimal, reversible" rule. Record the decision
and the reasoning in PROGRESS.md and move on.
