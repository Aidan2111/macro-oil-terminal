# Custom domain unblock checklist

This runbook is the "5-minute flip the switch" sequence for moving the
Macro Oil Terminal off the default Static Web App URL onto a custom
domain. Wave 5 backlog item #3.

> **Status (2026-04-26):** _Awaiting domain purchase by Aidan._
> Everything below is autonomous-ready — pick a domain, register it,
> and walk the steps in order. Total wall-clock once DNS exists is
> ~10–20 min (most of it waiting for Azure to issue the managed cert).

---

## 1. Decision context

The site lives at the default Azure-issued hostname:

```
https://delightful-pebble-00d8eb30f.7.azurestaticapps.net
```

That URL is fine for demos, but the brand polish — desk-grade trade
terminal, public thesis pages, eventual paywall — lands on a custom
domain. Three candidates that survived the brainstorm:

| Domain                  | Notes                                                                                                    |
| ----------------------- | -------------------------------------------------------------------------------------------------------- |
| `oilmonitor.app`        | **Default recommendation.** Matches the product name, `.app` is HSTS-preloaded so TLS is non-negotiable. |
| `oilmonitor.io`         | Shorter, cheaper to renew than `.app`, slightly less "this is a real product" cachet.                    |
| `oil.youbiquity.com`    | **Fastest path** — subdomain on Aidan's existing `youbiquity.com`. No new registration; just one CNAME.  |

If you want to be live in the next 30 minutes, pick
`oil.youbiquity.com`. If you want the standalone brand, pick
`oilmonitor.app`.

### Cost / timeline

- `.app` registration: ~$14–20/yr (Cloudflare $14, Namecheap $19).
- `.io` registration: ~$30–40/yr (premium TLD, no avoiding it).
- `.com` subdomain: $0 incremental (Aidan already owns
  `youbiquity.com`).
- DNS host recommendation: **Cloudflare** — free DNS, automatic CNAME
  flattening at the apex, free DDoS, easy to revoke if we change
  hosts later.
- Azure managed-cert issuance: usually 5–15 min after the CNAME
  validates. No cost on the SWA Free tier.

> **DO NOT register a domain on Aidan's behalf.** This runbook waits.

---

## 2. Once the domain is registered

Replace `<chosen-host>` everywhere below with the actual hostname
(e.g. `oilmonitor.app` or `oil.youbiquity.com`). Apex domains (e.g.
`oilmonitor.app` with no subdomain) need an ALIAS/ANAME or
Cloudflare's CNAME flattening; subdomains can use a plain CNAME.

### Step 1 — Add the DNS record at the registrar

For a subdomain (`oil.youbiquity.com`) or any non-apex:

```
Type:   CNAME
Name:   <chosen-host>           # e.g. "oil" for oil.youbiquity.com
Value:  delightful-pebble-00d8eb30f.7.azurestaticapps.net
TTL:    300
Proxy:  DNS-only (gray cloud) on Cloudflare — Azure needs to see the CNAME
```

For an apex (`oilmonitor.app`) on Cloudflare, use a CNAME at the
root with proxy off; Cloudflare flattens it to A/AAAA at query
time. On other registrars use ALIAS/ANAME if available, otherwise
move DNS to Cloudflare first.

Wait for the record to propagate:

```bash
dig +short <chosen-host>
# Expect: delightful-pebble-00d8eb30f.7.azurestaticapps.net.
#         <some IP>
```

### Step 2 — Bind the hostname to the Static Web App

```bash
az staticwebapp hostname set \
  --hostname <chosen-host> \
  -g oil-price-tracker \
  -n oil-tracker-web-0f18

az staticwebapp hostname show \
  --hostname <chosen-host> \
  -g oil-price-tracker \
  -n oil-tracker-web-0f18
```

The first command returns immediately; the cert provisioning happens
asynchronously. Re-run the `show` command every minute until you see:

```
"status": "Ready"
```

Typical: 5–15 minutes. If it stays in `Validating` past 30 minutes,
the CNAME isn't visible to Azure — re-check with `dig` and confirm
proxy is **off** if you're on Cloudflare.

### Step 3 — Update the AAD App Registration redirect URIs

OIDC sign-in (Wave 4 P1.1) is configured against the SWA URL today;
the new hostname needs to be added or sign-in will 400.

1. Azure Portal → **Microsoft Entra ID** → **App registrations** →
   the registration tied to this app (search for
   `oil-tracker` or the client ID stored in
   `AZURE_AD_CLIENT_ID` on the App Service config).
2. **Authentication** blade → **Redirect URIs**.
3. Add: `https://<chosen-host>/api/auth/callback/azure-ad`
4. Keep the old SWA redirect URI for now (rollback safety).
5. Save.

### Step 4 — Update the keep-warm workflow URL

File: `.github/workflows/keep-warm.yml`

Change the SWA ping line (currently line ~52):

```yaml
URL="https://delightful-pebble-00d8eb30f.7.azurestaticapps.net/build-info.txt"
```

to:

```yaml
URL="https://<chosen-host>/build-info.txt"
```

### Step 5 — Update the cd-nextjs SHA-verify URL (if uncommented)

File: `.github/workflows/cd-nextjs.yml`

The frontend SHA-verify block (lines ~228–243) is currently
commented out. If/when it gets re-enabled, the `URL=` constant
should point at `https://<chosen-host>` not the SWA hostname.

For now there is nothing to change in this file unless you are also
re-enabling the frontend live-verify step. Note in the PR description
either way.

### Step 6 — Update frontend metadata

File: `frontend/app/layout.tsx`

The `metadata` export currently has no `metadataBase`. Add it so
Open Graph / Twitter card image URLs resolve to the canonical
host:

```ts
export const metadata: Metadata = {
  metadataBase: new URL("https://<chosen-host>"),
  title: "Macro Oil Terminal",
  description:
    "Oil-spread dislocation research terminal — live quotes, trade theses, fleet tracking.",
  icons: {
    icon: "/favicon.ico",
  },
};
```

### Step 7 — Smoke test

```bash
curl -I https://<chosen-host>/
# Expect: HTTP/2 200, strict-transport-security header present
curl -I https://<chosen-host>/build-info.txt
# Expect: HTTP/2 200
curl -s https://<chosen-host>/build-info.txt
# Expect: sha=<latest> ... matches /api/build-info on the backend
```

Manually verify in a browser:

- [ ] Home page renders, ticker tape animates.
- [ ] `/fleet` globe loads (no mixed-content errors in console).
- [ ] OIDC sign-in round-trips (login → callback → home).
- [ ] No CSP violations in console (the Content-Security-Policy
      `connect-src` should already cover this since it allows
      same-origin; flag if you see `Refused to connect`).

### Step 8 — Commit and ship

```bash
git checkout -b feat/custom-domain-cutover-<chosen-host>
git add .github/workflows/keep-warm.yml frontend/app/layout.tsx
git commit -m "feat(infra): switch primary URL to <chosen-host>"
git push -u origin HEAD
gh pr create --base main --title "feat(infra): cut over primary URL to <chosen-host>"
```

After merge, re-run the smoke test on the merged commit.

---

## 3. Optional follow-ups (not blocking)

- Update the `BASE` constants in the `.agent-scripts/` Lighthouse +
  visual-audit scripts so future Lighthouse runs hit the canonical
  host. Functionally equivalent — both URLs serve the same SWA — so
  this is cosmetic.
- Update `SECURITY.md` "production URL" mention.
- Update `docs/architecture.md` if it embeds the SWA URL.
- Once you've watched the new domain stay green for ~7 days, remove
  the old SWA hostname from the AAD redirect URI list.

---

## 4. Rollback

If anything melts:

```bash
az staticwebapp hostname delete \
  --hostname <chosen-host> \
  -g oil-price-tracker \
  -n oil-tracker-web-0f18 --yes
```

The `delightful-pebble-…` URL keeps working throughout — Azure SWA
always serves on the platform hostname regardless of custom-domain
state — so a bad cutover is recoverable in seconds.

---

## File references for the cutover PR

- `.github/workflows/keep-warm.yml` — line ~52 (SWA ping URL)
- `.github/workflows/cd-nextjs.yml` — lines ~228–243 (commented
  SHA-verify; only if re-enabling)
- `frontend/app/layout.tsx` — `metadata` export, add `metadataBase`
- (after a few days) `SECURITY.md`, `docs/architecture.md`,
  `.agent-scripts/*.py` — cosmetic URL updates
