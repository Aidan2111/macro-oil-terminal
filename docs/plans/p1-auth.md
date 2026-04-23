# P1.1 — Auth + User Store (Plan)

> **Status:** APPROVED (2026-04-22). Brainstorm defaults adopted.
> Cutting the worktree.
> **Branch:** `feat/p1-auth` off `main`, worktree at
> `../macro_oil_terminal-p1-auth`.
> **Rhythm:** one fresh subagent per task, RED → GREEN → REFACTOR →
> commit, two-stage review (spec-compliance + code-quality) before the
> next task starts. Same loop we used for hero-thesis HT1..HT6.

## Definition of done

- Six unit tests + three e2e tests pass locally and in CI.
- `@requires_auth` decorator gates the (placeholder) execute button
  in the hero band.
- `auth/` package exists with the module layout in the design spec.
- `requirements.txt` bumps and the new Azure resources provisioned
  (storage account + Key Vault secrets) — provisioned by host via
  `az` CLI, not by CD.
- `.streamlit/secrets.toml.example` landed; real file gitignored.
- PROGRESS.md entry and brainstorm/design marked APPROVED.

---

## Task 1 — User dataclass + InMemoryUserStore

**Red:** add `tests/unit/test_auth_user.py` with:

1. `test_user_dataclass_round_trip` — construct a `User`, serialise to
   a plain dict via `dataclasses.asdict`, reconstruct, assert equality.
2. `test_in_memory_user_store_upsert_from_oidc_claims_creates` — given
   claims `{sub, email, name, picture}`, `upsert` returns a `User`
   with `created_at == updated_at` (both set to "now") and
   `get(sub)` returns the same row.
3. `test_in_memory_user_store_upsert_is_idempotent_on_second_call` —
   call `upsert` twice with the same sub; second returns the same
   row with `updated_at > created_at`.

**Green:** create `auth/__init__.py`, `auth/user.py` with the `User`
dataclass + `UserStore` Protocol + `InMemoryUserStore`.

**Refactor:** ensure no datetime comparisons depend on microsecond
resolution (sleep 1ms in test 3, or monkeypatch `datetime.utcnow`).

**Commit:** `feat(auth): User dataclass + InMemoryUserStore (P1.1.1)`.

---

## Task 2 — TableStorageUserStore

**Red:** add `tests/unit/test_auth_table_storage.py`:

1. `test_table_storage_user_store_upsert_translates_to_entity` —
   patch `azure.data.tables.TableClient`; assert `upsert_entity`
   called with a dict whose `PartitionKey == "users"` and
   `RowKey == <sub>`.
2. `test_table_storage_user_store_get_round_trip` — patch the
   client's `get_entity` to return a canned entity; assert
   `get(sub)` returns a `User` with the expected fields.
3. `test_table_storage_user_store_500_raises_useful_error` — mock
   raises `HttpResponseError`; store raises
   `auth.user.UserStoreError` with the original as `__cause__`.

**Green:** add `TableStorageUserStore` to `auth/user.py` plus
`UserStoreError`. Thin entity↔dataclass translation layer.

**Refactor:** pull the entity ↔ User mapping into two module-private
functions (`_entity_from_user`, `_user_from_entity`) for reuse in
future stores.

**Commit:** `feat(auth): TableStorageUserStore + UserStoreError (P1.1.2)`.

---

## Task 3 — current_user() + MOCK_AUTH_USER hook

**Red:** add `tests/unit/test_auth_session.py`:

1. `test_current_user_returns_none_when_unauth` — with no
   `MOCK_AUTH_USER`, no cookie, `current_user()` returns None.
2. `test_current_user_returns_mock_when_env_set_and_not_prod` — set
   `MOCK_AUTH_USER=a@b.c`, `STREAMLIT_ENV=dev`; `current_user()`
   returns a `User` with that email and a deterministic sub like
   `mock:<sha256(email)[:16]>`.
3. `test_current_user_ignores_mock_in_prod` — set `MOCK_AUTH_USER=a@b.c`
   AND `STREAMLIT_ENV=prod`; `current_user()` returns None.
4. `test_current_user_returns_real_user_when_st_user_logged_in` —
   stub `st.user` to return a logged-in user dict; `current_user()`
   returns a `User` with that sub/email, calls `user_store.upsert`
   exactly once.

**Green:** implement `auth/session.py`:
- `current_user() -> User | None`
- `_mock_user_from_env() -> User | None`
- `_user_from_streamlit_session() -> User | None`

**Refactor:** cache the result on `st.session_state["_auth_user"]` so
`current_user()` is cheap to call repeatedly inside a render.

**Commit:** `feat(auth): current_user() + MOCK_AUTH_USER testing seam (P1.1.3)`.

---

## Task 4 — @requires_auth decorator + render_login_gate widget

**Red:** add `tests/unit/test_auth_decorator.py`:

1. `test_requires_auth_passes_through_when_authed` — mock
   `current_user()` to return a User; decorated function runs and
   returns its normal value.
2. `test_requires_auth_renders_login_gate_when_unauthed` — mock
   `current_user()` to return None; decorated function does NOT run,
   captured `st.info` / `st.button` calls assert the gate rendered.
3. `test_render_login_gate_contains_tos_and_risk_links` — the gate
   text contains `"/legal/terms"` and `"/legal/risk"` substrings.

**Green:** implement `auth/__init__.py::requires_auth` +
`auth/widgets.py::render_login_gate`.

**Refactor:** use `functools.wraps`, keep widgets side-effect free
outside the Streamlit runtime by returning early when
`streamlit.runtime.exists()` is False (so unit tests don't blow up).

**Commit:** `feat(auth): @requires_auth + render_login_gate widget (P1.1.4)`.

---

## Task 5 — Wire into app.py (header signin + gated execute placeholder)

**Red:** add `tests/e2e/test_auth_public_and_gated.py`:

1. `test_public_research_visible_without_login` — page loads, hero
   band visible, tabs 1–3 visible, no auth gate overlay.
2. `test_sign_in_button_visible_when_unauth` — locator
   `[data-testid="signin-button"]` attached and has the expected
   "Sign in with Google" text.
3. `test_mock_auth_unlocks_user_caption` — set `MOCK_AUTH_USER`
   env in the Playwright launch, reload, locator
   `[data-testid="signed-in-as"]` contains the mock email.

**Green:** add `render_header_signin()` + `render_execute_button_stub()`
(gated via `@requires_auth`) to `app.py`. Attach
`data-testid="signin-button"` / `"signed-in-as"` for Playwright.

**Refactor:** pull the header row into a helper alongside the other
hero-band helpers so the hero band retains a single render-tree.

**Commit:** `feat(auth): header signin + gated execute stub in hero band (P1.1.5)`.

---

## Task 6 — Azure provisioning scripts + CD env wiring

**Red:** add `tests/unit/test_auth_config.py`:

1. `test_missing_env_vars_sets_degraded_flag` — with no env
   vars, `auth.is_configured()` returns False and a module-level
   warning logs once.
2. `test_fully_configured_env_returns_true` — set all four env
   vars; `is_configured()` returns True.
3. `test_prod_requires_configured` — set `STREAMLIT_ENV=prod`
   AND missing env vars; `auth.boot_check()` raises
   `AuthNotConfigured`.

**Green:** implement `auth/__init__.py::is_configured` +
`boot_check`. Call `boot_check()` at the top of `app.py` (wrap in
try/except so dev doesn't explode).

Also add:

- `infra/provision_auth.sh` — idempotent script: creates storage
  account, `users` table, three Key Vault secrets (client id /
  client secret / cookie secret), sets four App Service app
  settings referencing Key Vault.
- `.streamlit/secrets.toml.example` with `env:*` placeholders.
- Bump `requirements.txt` (`streamlit>=1.42.0`, `azure-data-tables`,
  `authlib` pin).
- Update `.github/workflows/cd.yml` if needed (no new steps expected —
  env vars come from App Service).

**Refactor:** document in `DEPLOY.md` which secrets need to exist in
Key Vault before first deploy.

**Commit:** `feat(auth): Azure provisioning + config boot check (P1.1.6)`.

---

## Task 7 — Finishing flow (separate task, not RED/GREEN)

This is the `finishing-a-development-branch` skill.

1. Merge `main` into `feat/p1-auth`; resolve conflicts.
2. Run full pytest locally — all 9 auth tests + the existing 161
   hero-thesis-era tests must pass.
3. Run Playwright locally headed, screenshot the signed-in state for
   PROGRESS.md.
4. Aidan runs `infra/provision_auth.sh` on the host (one-shot
   provisioning — "Waiting on Aidan" signup item).
5. Push the branch; open PR; CI runs.
6. CD to `oil-tracker-app-canadaeast-4474`.
7. Live verify: unauth view renders, sign-in button renders,
   real Google round-trip works end-to-end for `aidan@youbiquity.com`.
8. Merge to main; delete worktree + remote branch.
9. PROGRESS.md entry.
10. Mark tasks 80–84 complete.

**Commit:** `Merge feat/p1-auth: user auth + gated execute stub (P1.1)`.

---

## Open risks / known unknowns

- `st.login()` semantics might subtly differ on Azure App Service
  (behind a reverse proxy) — websocket/cookie domain mismatch is the
  classic bug. Mitigation: ship Task 6 with a health endpoint that
  returns the current cookie name, and live-verify after CD.
- Google OAuth consent screen review — if we ever ask for scopes
  beyond `openid email profile`, the app goes into a Google review
  queue (weeks). We don't, so we're fine.
- Streamlit 1.42's `st.login` API has evolved twice already in 2025;
  if they rename arguments, the test suite catches it in CI.

## Checklist to greenlight the plan

- [ ] Aidan has greenlit the six open questions in the brainstorm.
- [ ] `az`/`gh` login confirmed on host (already — from hero-thesis).
- [ ] GCP OAuth client id + secret captured (waiting on Aidan).
- [ ] Storage account region + RG approved (`canadaeast`,
      `oil-price-tracker`).

---

## Clerk pivot plan (2026-04-22 00:40Z)

Short rebuild on a new branch `feat/p1-auth-clerk` off `main` (main
already has the Google-OIDC P1.1 merged as `3f39ff4`).

**Four TDD tasks**, each fresh subagent, RED→GREEN→REFACTOR→commit.
Tasks 1 and 2 are independent; 3 depends on 2; 4 depends on 3.

### Task C1 — Env-var swap + strip Google-specific wiring

- `auth/config.py`: `_REQUIRED_ENV_VARS` becomes
  `("CLERK_PUBLISHABLE_KEY", "CLERK_SECRET_KEY", "STREAMLIT_COOKIE_SECRET")`.
- `tests/unit/test_auth_config.py`: the 5 existing tests re-expressed
  against the new var list. No test count change.
- `.env.example`: drop Google block, add Clerk block.
- `.streamlit/secrets.toml.example`: drop `[auth]` + `[auth.google]`;
  leave a short comment pointing at Clerk App Settings.
- `infra/provision_auth.sh`: swap the two `read` prompts; write
  `clerk-publishable-key` + `clerk-secret-key` KV secrets; set
  `CLERK_PUBLISHABLE_KEY` + `CLERK_SECRET_KEY` App Settings; drop
  the three Google-specific writes.
- Commit: `feat(auth): swap env vars Google → Clerk (P1.1-clerk C1)`.

### Task C2 — `auth/clerk.py` with JWT verify + sign-in URL helpers

- New `auth/clerk.py` with: `clerk_subdomain_from_publishable_key`,
  `clerk_jwks_url`, `clerk_sign_in_url`, `clerk_sign_out_url`,
  `verify_clerk_jwt`.
- Add `PyJWT[crypto]>=2.8.0` to `requirements.txt`.
- Module-level JWKS cache (10-minute TTL) fetched via `requests.get`.
  Tests monkeypatch the fetcher to return a canned JWKS.
- `tests/unit/test_auth_clerk.py` — 4 tests:
  C2.1 verify valid signature round-trip,
  C2.2 invalid signature returns None,
  C2.3 expired token returns None,
  C2.4 `clerk_sign_in_url("https://x/y")` url-encodes the redirect.
  Use `cryptography.hazmat.primitives.asymmetric.rsa` to generate a
  2048-bit keypair once in a fixture; sign with `pyjwt.encode(...,
  algorithm="RS256", headers={"kid": "test"})`.
- Commit: `feat(auth): auth/clerk.py — JWT verify + sign-in URL helpers (P1.1-clerk C2)`.

### Task C3 — Rewire `auth/session.py` Clerk branch

- Replace `_user_from_streamlit_session` with `_user_from_clerk_session`.
  Reads `__clerk_db_jwt` from `st.query_params`; if present calls
  `auth.clerk.verify_clerk_jwt(token)`; if valid, upserts the store,
  caches the User in `st.session_state["_auth_user"]`, and clears
  the query param.
- Keep the `MOCK_AUTH_USER` path + the `STREAMLIT_ENV=prod` safety-net
  byte-for-byte.
- `tests/unit/test_auth_session.py`: the `test_current_user_returns_real_user_…`
  test renames to `test_current_user_verifies_clerk_jwt_from_query_params`
  and monkeypatches `auth.clerk.verify_clerk_jwt` + a fake
  `st.query_params` + `st.session_state`. Idempotency test
  (`test_current_user_cached_across_calls_within_session`) preserved.
- Commit: `feat(auth): current_user() reads Clerk JWT from query_params (P1.1-clerk C3)`.

### Task C4 — Widgets + e2e + live-verify update

- `auth/widgets.py`: `_render_header_signin` (currently in `app.py`)
  renders `st.link_button("Sign in", url=clerk_sign_in_url(app_url))`
  when unauthed, with the existing `data-testid="signin-button"`
  sentinel div above it. Sign-out link → `clerk_sign_out_url(app_url)`.
- `app.py`: unchanged surface, but `_render_header_signin` now delegates
  to `auth.widgets.render_header_signin` (move the helper into the
  package; leave the tier-tile execute stub as-is).
- `tests/e2e/test_auth_public_and_gated.py`: `test_sign_in_button_visible_when_unauth`
  adds one assertion — the anchor's `href` contains `clerk.accounts.dev`.
- `.agent-scripts/verify_p1_auth_live.py`: grep the rendered DOM
  for a `clerk.accounts.dev` href; fail if absent when unauthed.
- Commit: `feat(auth): sign-in link targets Clerk hosted UI (P1.1-clerk C4)`.

### Finishing flow (Task C5)

1. Merge `main` into `feat/p1-auth-clerk` (should be clean — main
   hasn't moved since P1.1 merge + PROGRESS commit).
2. Full pytest + e2e locally. Target: **182 passed** (same count —
   Clerk tests replace Google tests 1:1, plus 4 new `test_auth_clerk`
   offset by 4 old passing).
3. `git push -u origin feat/p1-auth-clerk` → PR → CI → CD.
4. Live verify: button renders, href points at Clerk.
5. Merge `feat/p1-auth-clerk` → `main` via `--no-ff`. CD redeploys.
6. Delete worktree + branch (local + remote).
7. PROGRESS.md entry.

### Env / signup state

- **Waiting on Aidan (parallel signup task):** Clerk publishable key
  + secret key + the hosted subdomain. Until they land in App
  Settings, the deployed site runs in "auth-not-fully-configured"
  mode — the boot-check banner shows and the signin link is inert
  (it still renders at a Clerk URL built from a placeholder
  subdomain if env is empty, but clicking it 404s until the real
  key is present).


---

## See also — UI polish pass plan

The active work has moved to `docs/plans/ui-polish.md` on branch
`feat/ui-polish-pass`. The P1.1-clerk section above is ARCHIVED.

