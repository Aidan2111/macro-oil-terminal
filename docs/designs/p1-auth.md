# P1.1 — Authentication + User Store (Design spec)

> **Status:** ARCHIVED (2026-04-22 00:55Z). Two pivots in, ending up
> with a simplified single-user product scope: the shipped P1.1
> Google-OIDC infrastructure remains (merged at `3f39ff4`), but no
> IdP is actively wired. UI polish has been promoted to the
> critical path. This doc, including the Clerk pivot section, is
> preserved as a warm-start for any future multi-user return.

## One-paragraph summary

We use Streamlit's native `st.login()` (v1.42+) with a single OIDC
provider — Google — and keep the session in Streamlit's built-in
signed cookie. On first login, we upsert a user row into an Azure
Table Storage `users` table keyed by Google's stable `sub` identifier.
Render-time gates are a single `@requires_auth` decorator + a cheap
`auth.current_user()` helper. Public research, hero thesis, track
record stay public. Execute-this-trade, positions, notifications, and
onboarding gate behind auth. Tests bypass OAuth via
`MOCK_AUTH_USER=<email>` (dev-only, blocked in prod by a second env
guard).

## Module surface

New files:

```
auth/
  __init__.py         # re-exports current_user, requires_auth, sign_in, sign_out
  user.py             # User dataclass + UserStore ABC + TableStorageUserStore
  session.py          # current_user(), require_auth() logic; MOCK_AUTH_USER hook
  widgets.py          # render_header_signin(), render_login_gate()
```

New infra:

- Storage account `oiltrackerstore4474` (co-located in `canadaeast`,
  same RG) with one Table `users`.
- Google Cloud OAuth 2.0 client (Web application) in a dedicated GCP
  project `macro-oil-terminal`.
- Two new secrets in Azure Key Vault (`oil-tracker-kv`):
  - `google-oauth-client-id`
  - `google-oauth-client-secret`
  - `streamlit-cookie-secret` (64 random bytes, base64).
- Two new App Service app settings wiring Key Vault references:
  - `GOOGLE_OAUTH_CLIENT_ID`
  - `GOOGLE_OAUTH_CLIENT_SECRET`
  - `STREAMLIT_COOKIE_SECRET`
  - `STORAGE_ACCOUNT_CONNECTION_STRING` (or managed-identity
    + `STORAGE_ACCOUNT_NAME`)

## Streamlit secrets.toml shape

```toml
# .streamlit/secrets.toml (NOT committed; values from env on Azure)

[auth]
redirect_uri = "https://oil-tracker-app-canadaeast-4474.azurewebsites.net/oauth2callback"
cookie_secret = "env:STREAMLIT_COOKIE_SECRET"

[auth.google]
client_id = "env:GOOGLE_OAUTH_CLIENT_ID"
client_secret = "env:GOOGLE_OAUTH_CLIENT_SECRET"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
client_kwargs = { scope = "openid email profile" }
```

We wire this in `app.py` once at boot — Streamlit reads the block on
startup. For local dev, `.streamlit/secrets.toml.example` is committed
and the real file is gitignored.

## User dataclass

```python
# auth/user.py
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class User:
    sub: str                  # Google subject id — stable PK
    email: str
    name: str
    picture_url: str | None
    created_at: datetime
    updated_at: datetime
    alpaca_refresh_token_ref: str | None = None     # P1.2 will populate
    alpaca_mode: str | None = None                   # "paper" | "live"
    notification_prefs_json: str = "{}"              # P1.7 will populate
    onboarding_completed_at: datetime | None = None  # P1.6 will populate
```

## UserStore ABC

```python
# auth/user.py
class UserStore(Protocol):
    def get(self, sub: str) -> User | None: ...
    def upsert_from_oidc_claims(self, claims: dict) -> User: ...
    def update_preferences(self, sub: str, **fields) -> User: ...
```

Two implementations:

- `TableStorageUserStore` — production path, wraps `azure-data-tables`.
- `InMemoryUserStore` — tests use this; dict-backed.

`auth.get_store()` returns the right one based on
`AUTH_USER_STORE` env var (`table` default, `memory` for tests).

## Auth gate — two flavours

### Render-time widget gate (primary)

```python
from auth import requires_auth, current_user

@requires_auth
def _render_execute_button(thesis, tier):
    ...

# at call site
_render_execute_button(thesis, tier)
```

If no user: the decorator renders a `st.info("Sign in with Google to
execute trades")` + a Google-branded sign-in button and returns
early. No redirect, no page reload — the public research view keeps
rendering below.

### Route-level gate (secondary)

For pages like onboarding (P1.6) where the *entire* page requires
auth, the render function calls `require_auth()` (raises
`st.stop()` after showing the login gate if not signed in).

## Sign-in / sign-out flow

1. User clicks **Sign in with Google** (widget in the hero-band header
   row).
2. `st.login("google")` — Streamlit redirects to Google.
3. Google redirects back to `/oauth2callback?code=...`.
4. Streamlit exchanges the code for an id-token + access-token, writes
   the signed cookie, and populates `st.user`.
5. Our app-boot hook (`_bootstrap_user()` at the top of `app.py`) calls
   `user_store.upsert_from_oidc_claims(st.user.to_dict())` — this
   creates the user row on first login, or bumps `updated_at` on
   subsequent logins.
6. `current_user()` now returns a `User` dataclass for the rest of
   the render pass.
7. **Sign out** — `st.logout()` clears the cookie. Session state is
   dropped. Render falls back to the unauthed hero band.

## Testing seam

- `MOCK_AUTH_USER` env var holds an email (e.g. `aidan@youbiquity.com`).
- `STREAMLIT_ENV` env var must not equal `prod` for the mock to apply.
- `auth.current_user()` checks `MOCK_AUTH_USER` first — if set,
  returns a synthetic `User` with a fixed `sub` and that email.
- App Service sets `STREAMLIT_ENV=prod` explicitly so the mock can't
  accidentally apply there.

### Tests we ship in P1.1

Unit (pytest):

1. `User` dataclass round-trip (serialise to Table Storage entity + back).
2. `InMemoryUserStore.upsert_from_oidc_claims` creates then updates
   (idempotent).
3. `TableStorageUserStore.upsert_from_oidc_claims` — uses a mock
   `TableClient` via `azure-data-tables`' test utilities.
4. `current_user()` returns mock user when `MOCK_AUTH_USER` set
   AND `STREAMLIT_ENV != "prod"`.
5. `current_user()` returns `None` when `MOCK_AUTH_USER` set AND
   `STREAMLIT_ENV == "prod"` (safety-net for accidental env leak).
6. `@requires_auth` renders a login prompt when user is None (assert
   the prompt string appears).

E2E (Playwright):

7. `test_public_research_visible_without_login` — hit root, verify
   hero band + tabs 1–3 render, no auth gate.
8. `test_execute_button_gated` — hero-band tier tile shows a "Sign
   in to execute" caption, not an active execute button, when
   unauthed.
9. `test_mock_auth_unlocks_execute` — set `MOCK_AUTH_USER`, reload,
   execute button is now active (stubbed; P1.3 will make it fire
   an order).

## Public-vs-gated surface map

| Surface | Gate |
| --- | --- |
| Hero thesis band | Public |
| Sign-in / sign-out header controls | Public (renders "Sign in" button when unauthed) |
| Portfolio-size input | Public (session-state only) |
| Tier tiles — display | Public |
| Tier tiles — "Execute" button | **Auth required** (P1.3) |
| Pre-trade checklist | Public (session-state only) |
| Tab 1 Macro arbitrage | Public |
| Tab 2 Depletion forecast | Public |
| Tab 3 Fleet analytics | Public |
| Live positions panel (P1.4) | **Auth required** |
| Track record page (P1.5) | Public |
| Notifications settings (P1.7) | **Auth required** |
| Onboarding wizard (P1.6) | **Auth required** |
| Legal pages /legal/* (P1.9) | Public |

## Disclaimers / legal touch points

- Sign-in button caption reads verbatim: *"Sign in with Google — by
  continuing you accept our [Terms] and [Risk Disclosure]."* Brackets
  link to `/legal/terms` and `/legal/risk` (P1.9 delivers the pages).
- Post-login, the existing "Research & education only. Not personalized
  financial advice…" disclaimer in the hero band remains visible.
- P1.9 ships the legal pages in parallel. P1.1 links to them even if
  the pages land a day later — 404 briefly is OK during rollout.

## Error modes and fallbacks

1. **Google OIDC down** — `st.login()` raises. We catch at the
   widget level, render `st.error("Sign-in is temporarily unavailable.
   Public research remains available below.")`, and the rest of the
   page keeps rendering.
2. **Table Storage 500** — `upsert_from_oidc_claims` fails. We log
   and set `session_state["auth_degraded"]=True`. `current_user()`
   returns a transient in-memory `User` constructed from OIDC claims
   only; gates still open, but we don't persist the update. Banner
   tells the user "Some account features unavailable — retry in a
   few minutes."
3. **Cookie tampered / expired** — Streamlit handles; user is
   signed out and sees the public view again.
4. **Missing env vars** — app boot logs a hard warning; the "Sign in"
   button renders a `st.error("Auth not configured on this
   deployment")` toast on click. Public research still works.

## Migration notes

- Existing data in `data/trade_executions.jsonl` has no user id
  (hero-thesis appended without auth). Schema bump adds `user_sub:
  str | None`; rows with `None` are grandfathered as "pre-auth
  exec". P1.3 writes the real `sub` from `current_user()`.
- Bump `requirements.txt`: `streamlit>=1.42.0`, add
  `azure-data-tables>=12.5.0`, add `authlib>=1.3.0` (Streamlit's
  transitive dep, pin explicitly so we don't get a surprise bump).

## Out of scope for P1.1 (explicit)

- Alpaca OAuth (P1.2).
- Execute this-trade wiring to broker (P1.3).
- Live positions panel (P1.4).
- Track record aggregation / public route (P1.5).
- Onboarding wizard (P1.6).
- Notifications (P1.7).
- Mobile polish (P1.8).
- Legal pages (P1.9 — parallel branch).
- Stripe / paywall (Phase 2).
- MFA, email verification, password reset (not needed — Google OIDC
  handles).

## Acceptance criteria

- `streamlit run app.py` locally with `MOCK_AUTH_USER` unset and
  `.streamlit/secrets.toml` populated renders the public view, a
  Google "Sign in" button, and after a successful Google round-trip,
  the signed-in view with `st.user.email` visible in the header.
- All P1.1 tests (6 unit + 3 e2e) pass locally and in CI.
- A user row exists in the `users` Table after first login.
- The public research view (hero thesis, tabs 1–3, track record) is
  reachable without a session cookie.
- `MOCK_AUTH_USER` cannot bypass auth when `STREAMLIT_ENV=prod`
  (covered by test 5).
- CD deploys cleanly to `oil-tracker-app-canadaeast-4474` with the
  new Key Vault secrets wired, health-check green.

## Reversibility

- Swap Google → Clerk / Auth0 / Microsoft: change
  `.streamlit/secrets.toml` block, add the new OIDC provider's env
  vars. No code changes.
- Swap Table Storage → Cosmos / Postgres: implement a second
  `UserStore` class, flip `AUTH_USER_STORE`. User data migrates via
  a one-off script reading the source's iteration API.
- Rip out entirely: delete `auth/`, remove decorators. Left with the
  pre-P1.1 public dashboard.

---

## Clerk pivot (2026-04-22 00:40Z)

Design delta — what changes from the Google-OIDC shape above. Everything
not mentioned here stays as shipped.

### New module: `auth/clerk.py`

```python
"""Clerk JWT verification + hosted sign-in URL helpers."""

def clerk_subdomain_from_publishable_key(pk: str) -> str: ...
def clerk_jwks_url() -> str: ...                    # derives from env or override
def clerk_sign_in_url(redirect_url: str) -> str: ... # https://<sub>.clerk.accounts.dev/sign-in?redirect_url=...
def clerk_sign_out_url(redirect_url: str) -> str: ...
def verify_clerk_jwt(token: str) -> dict | None: ... # returns verified claims, None on invalid
```

`verify_clerk_jwt` fetches the JWKS (cached for 10 min), picks the key
matching the token's `kid`, and verifies RS256 signature + `iss` +
`exp` + `nbf`. Returns a dict with at minimum `{sub, email, name, picture}`.

### `auth/session.py` rewrite (surgical)

Swap the `_user_from_streamlit_session` branch for
`_user_from_clerk_session()`:

```python
def _user_from_clerk_session() -> User | None:
    # 1. If we cached a user this session, reuse.
    # 2. Else look for __clerk_db_jwt in st.query_params (the handshake token).
    # 3. If present, verify via auth.clerk.verify_clerk_jwt(token).
    # 4. If valid: upsert user store from claims, cache, strip the token
    #    from the URL with st.query_params.clear("__clerk_db_jwt"), return User.
    # 5. If no token AND no cached user: return None.
```

The `MOCK_AUTH_USER` short-circuit + `STREAMLIT_ENV=prod` safety-net
stay exactly as shipped. No Playwright / test-surface change for
those paths.

### `auth/widgets.py` delta

`render_login_gate` + `_render_header_signin` change the button into
a link rendered via `st.link_button("Sign in", url=clerk_sign_in_url(...))`.
The `data-testid="signin-button"` sentinel stays. On sign-out, link
to `clerk_sign_out_url(return_to=<app root>)` + call
`clear_cached_user()` when the user lands back.

### `auth/config.py` delta

Required env vars become:
- `CLERK_PUBLISHABLE_KEY`
- `CLERK_SECRET_KEY`
- `STREAMLIT_COOKIE_SECRET` (unchanged — used for our own session cookie, not Clerk's)
- `STORAGE_ACCOUNT_CONNECTION_STRING` (or `_NAME` — unchanged).

Optional: `CLERK_JWKS_URL` (override; default derived from publishable key).

### `infra/provision_auth.sh` delta

Replace the two Google prompts:

```bash
read -p "Clerk publishable key (pk_live_... or pk_test_...): " CLERK_PK
read -s -p "Clerk secret key (sk_live_... or sk_test_...): " CLERK_SK
```

Write `clerk-publishable-key` and `clerk-secret-key` to Key Vault.
Key Vault reference names for App Settings:
`CLERK_PUBLISHABLE_KEY` / `CLERK_SECRET_KEY`.

Drop the three Google-specific secret writes.

### `.streamlit/secrets.toml.example` delta

Delete the `[auth]` + `[auth.google]` blocks (Streamlit's native
`st.login()` is no longer in the path). Replace with a short commented
reminder that Clerk env vars come from App Settings / `.env` in dev.

### `.env.example` delta

Drop `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET`. Add
`CLERK_PUBLISHABLE_KEY` / `CLERK_SECRET_KEY` / `CLERK_JWKS_URL=`
(blank default — derived from publishable key).

### `requirements.txt` delta

Add `PyJWT[crypto]>=2.8.0` for JWT verify (installs `cryptography`
transitively). Drop nothing — `streamlit>=1.42.0` still useful for
`st.context.cookies` and `st.link_button`.

### Test delta

- **New:** `tests/unit/test_auth_clerk.py` — 4 tests:
  1. `test_verify_clerk_jwt_valid_signature` — sign a token with a
     test RSA key, expose JWKS via a monkeypatch'd fetcher, verify
     returns the claims dict.
  2. `test_verify_clerk_jwt_invalid_signature` — tamper with the
     token; verify returns `None`.
  3. `test_verify_clerk_jwt_expired` — `exp` in the past; verify
     returns `None`.
  4. `test_clerk_sign_in_url_contains_redirect` — `clerk_sign_in_url("https://x/y")`
     returns a URL whose `redirect_url` query param equals the input.

- **Updated:** `tests/unit/test_auth_session.py` — rename the
  `test_current_user_returns_real_user_when_st_user_logged_in` test
  to `test_current_user_returns_real_user_when_clerk_jwt_in_query_params`;
  stub `auth.clerk.verify_clerk_jwt` to return fake claims; confirm
  the `MOCK_AUTH_USER` tests are unchanged (still 5 total).

- **Updated:** `tests/unit/test_auth_config.py` — the required env
  vars change; updated assertions list the new Clerk vars. Still 5
  tests.

- **Updated:** `tests/e2e/test_auth_public_and_gated.py` — the
  `test_sign_in_button_visible_when_unauth` test now also asserts
  the link's `href` contains `clerk.accounts.dev`. Three e2e tests
  total, unchanged.

- **Unchanged:** `test_auth_user.py` (3), `test_auth_table_storage.py` (4),
  `test_auth_decorator.py` (4).

- **Net:** 18 unit + 3 e2e = 21 tests, same count as P1.1. Clerk
  tests replace the Google-specific test, plus a new clerk module
  file.

### Live-verify delta

`.agent-scripts/verify_p1_auth_live.py` adds one more assertion —
the sign-in link's `href` attribute contains `clerk.accounts.dev`.

### Acceptance criteria delta

- Redirect to `clerk.accounts.dev/sign-in` + sign-up / sign-in via
  email or GitHub works end-to-end.
- On redirect back, `__clerk_db_jwt` is verified, claims land in
  the user store, and the "Signed in as <email>" caption renders.
- With `STREAMLIT_ENV=prod` and Clerk env unset, `boot_check()`
  raises → app.py try/except catches → "Auth not fully configured"
  banner appears, public research still works.
- All 21 tests pass locally and in CI.

