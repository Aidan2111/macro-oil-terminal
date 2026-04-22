# ADR 0003: OIDC for GitHub → Azure CD (no client secret)

* Status: accepted
* Date: 2026-04-22
* Deciders: @Aidan2111

## Context

CD needs to deploy the repo to Azure App Service on every push to
`main`. The historical option is to create a service-principal client
secret and store it as a GitHub Actions secret. That secret never
rotates cleanly, leaks into audit logs, and a compromised fork can
exfiltrate it.

GitHub Actions supports OpenID Connect (OIDC) federated credentials
against Entra ID — a short-lived token minted per run, tied to a
specific repo + ref. No long-lived secret anywhere.

## Decision

Use OIDC federated credentials exclusively. Specifically:

1. Created Entra app registration `macro-oil-terminal-cd`
   (appId `9d8ae4e7-d5f1-49cc-b6e3-b62cf1ad23a8`).
2. Created the matching Service Principal.
3. Assigned `Contributor` scoped narrowly to the `oil-price-tracker`
   resource group (not the subscription).
4. Attached three federated credentials:
   - `repo:Aidan2111/macro-oil-terminal:ref:refs/heads/main`
   - `repo:Aidan2111/macro-oil-terminal:pull_request`
   - `repo:Aidan2111/macro-oil-terminal:environment:production`
5. Stored `AZURE_CLIENT_ID` / `AZURE_TENANT_ID` /
   `AZURE_SUBSCRIPTION_ID` as GitHub repo secrets. **No client secret.**

The CD workflow sets `permissions: id-token: write, contents: read` and
uses `azure/login@v2` — the login step exchanges the GitHub-issued
token for a short-lived Azure token.

## Consequences

**Positive:**

- No long-lived credential exists anywhere that a fork, a leaked env,
  or a badly-scoped bot token could abuse.
- Permission changes are centralised on the Entra app — rotate a
  credential in seconds, no repo changes needed.
- Role assignment is narrower than "owner of subscription" — smallest
  blast radius that still lets CD write App Settings, deploy zip,
  update deployments.

**Negative / trade-offs:**

- Subject-claim shape depends on the workflow config — the initial
  push failed because the `environment: production` block emits a
  different subject than plain `refs/heads/main`, and we had to add
  a third federated cred. Contributors editing the workflow need to
  know this.
- Requires Entra Owner perms on the subscription to bootstrap the app
  registration + role assignment. Documented in `DEPLOY.md`.

## Alternatives considered

- **Client secret** — rejected, standard reasons (rotation pain,
  leakage risk).
- **Publish profile** — rejected, coarser credential + ties to one
  Web App only.
- **User-assigned managed identity on a self-hosted runner** —
  rejected, too much infra for a single-repo CD.

## References

- Commit `71b3d93` — `ci(cd): OIDC-based GitHub Actions deploy to Azure Web App`
- Commit `30bbfb1` — `docs: CD badge + deploy section + log CD round-trip`
- `SECURITY.md` — secret-handling posture
- `DEPLOY.md` — the SP/OIDC bootstrap commands
