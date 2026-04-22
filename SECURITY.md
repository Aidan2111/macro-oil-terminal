# Security

## Reporting

Open a GitHub Security Advisory on `Aidan2111/macro-oil-terminal` or email
the repo owner directly. Please do not open a public issue for vulnerability
disclosures.

## Secret handling

All secrets live as environment variables or cloud App Settings.
No secret is ever committed to the repo.

* `AZURE_OPENAI_*` — set as Azure App Service App Settings.
* `AISSTREAM_API_KEY` — optional, local `.env` or App Setting.
* `FRED_API_KEY`, `TWELVEDATA_API_KEY`, `ALERT_SMTP_*` — optional.
* Azure CD uses **OIDC federated credentials** — no long-lived Azure client secret.

`.gitignore` excludes `.env`, `.env.*` (except `.env.example`), `data/`, and
CLI-written session files under `.agent-scripts/`.

Pre-commit `gitleaks` (opt-in via `.pre-commit-config.yaml`) catches
accidental commits. GitHub secret scanning + CodeQL (`.github/workflows/codeql.yml`)
run on every push and weekly on a cron.

## Browser security headers (CSP) — known limitation

Streamlit serves its own `/` route without letting us inject custom
response headers — no `Content-Security-Policy`, `X-Frame-Options`, or
`Strict-Transport-Security` customisation without a reverse-proxy.
App Service terminates TLS, gives us HSTS implicitly, and denies
`iframe` embedding by default via its edge settings.

If you need strict CSP beyond that (for embedding this dashboard behind
another product, for example), the shortest path is:

1. Put nginx or Caddy in front of Streamlit inside the container, add a
   `startup.sh` that launches both.
2. Or upgrade to an App Service plan that supports a custom web.config
   with headers.

Until that's warranted, we accept Streamlit's defaults. This is documented
here so the decision is explicit rather than silent.
