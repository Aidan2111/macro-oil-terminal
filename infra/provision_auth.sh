#!/usr/bin/env bash
# Idempotent auth provisioning for Macro Oil Terminal (P1.1.6).
#
# Creates:
#   - Storage account (if missing) + "users" table.
#   - Three Key Vault secrets:
#       google-oauth-client-id, google-oauth-client-secret,
#       streamlit-cookie-secret, storage-connection-string.
#   - Four App Service settings referencing Key Vault + two plain
#     settings (STREAMLIT_ENV=prod, AUTH_USER_STORE=table).
#
# Safe to re-run. Each step checks before creating. Requires an active
# `az login` session with Contributor on the RG and Key Vault access.

set -euo pipefail

RG="${RG:-oil-price-tracker}"
LOCATION="${LOCATION:-canadaeast}"
STORAGE="${STORAGE:-oiltrackerstore4474}"
KV="${KV:-oil-tracker-kv}"
WEBAPP="${WEBAPP:-oil-tracker-app-canadaeast-4474}"

echo "== Macro Oil Terminal — auth provisioning =="
echo "RG=${RG}  LOCATION=${LOCATION}  STORAGE=${STORAGE}  KV=${KV}  WEBAPP=${WEBAPP}"
echo

# 1. Storage account ---------------------------------------------------------
if az storage account show --name "${STORAGE}" --resource-group "${RG}" --output none 2>/dev/null; then
    echo "[1/7] storage account ${STORAGE} exists — skip"
else
    echo "[1/7] creating storage account ${STORAGE}"
    az storage account create \
        --name "${STORAGE}" \
        --resource-group "${RG}" \
        --location "${LOCATION}" \
        --sku Standard_LRS \
        --kind StorageV2 \
        --min-tls-version TLS1_2 \
        --allow-blob-public-access false \
        --output none
fi

# 2. Users table -------------------------------------------------------------
echo "[2/7] ensuring 'users' table exists"
az storage table create \
    --name users \
    --account-name "${STORAGE}" \
    --auth-mode login \
    --output none

# 3. Cookie secret (Key Vault) -----------------------------------------------
if az keyvault secret show --vault-name "${KV}" --name streamlit-cookie-secret --output none 2>/dev/null; then
    echo "[3/7] streamlit-cookie-secret already present — skip"
else
    echo "[3/7] generating + storing streamlit-cookie-secret"
    COOKIE_SECRET="$(openssl rand -base64 48)"
    az keyvault secret set \
        --vault-name "${KV}" \
        --name streamlit-cookie-secret \
        --value "${COOKIE_SECRET}" \
        --output none
    unset COOKIE_SECRET
fi

# 4. Google OAuth secrets (interactive; skip each if already present) --------
HAVE_CID=0
HAVE_CSEC=0
if az keyvault secret show --vault-name "${KV}" --name google-oauth-client-id --output none 2>/dev/null; then
    HAVE_CID=1
fi
if az keyvault secret show --vault-name "${KV}" --name google-oauth-client-secret --output none 2>/dev/null; then
    HAVE_CSEC=1
fi

if [[ "${HAVE_CID}" -eq 1 && "${HAVE_CSEC}" -eq 1 ]]; then
    echo "[4/7] google-oauth-* secrets already present — skip"
else
    echo "[4/7] need Google OAuth credentials from https://console.cloud.google.com/apis/credentials"
    if [[ "${HAVE_CID}" -eq 0 ]]; then
        read -r -p "Google client_id: " CID
        az keyvault secret set \
            --vault-name "${KV}" \
            --name google-oauth-client-id \
            --value "${CID}" \
            --output none
        unset CID
    fi
    if [[ "${HAVE_CSEC}" -eq 0 ]]; then
        read -r -s -p "Google client_secret: " CSEC
        echo
        az keyvault secret set \
            --vault-name "${KV}" \
            --name google-oauth-client-secret \
            --value "${CSEC}" \
            --output none
        unset CSEC
    fi
fi

# 5. Storage connection string (Key Vault) -----------------------------------
echo "[5/7] refreshing storage-connection-string in Key Vault"
CONN_STR="$(az storage account show-connection-string \
    --name "${STORAGE}" \
    --resource-group "${RG}" \
    --query connectionString \
    --output tsv)"
az keyvault secret set \
    --vault-name "${KV}" \
    --name storage-connection-string \
    --value "${CONN_STR}" \
    --output none
unset CONN_STR

# 6. App Service settings ----------------------------------------------------
echo "[6/7] wiring App Service settings on ${WEBAPP}"
KV_REF() { echo "@Microsoft.KeyVault(SecretUri=https://${KV}.vault.azure.net/secrets/${1}/)"; }

az webapp config appsettings set \
    --resource-group "${RG}" \
    --name "${WEBAPP}" \
    --settings \
        "GOOGLE_OAUTH_CLIENT_ID=$(KV_REF google-oauth-client-id)" \
        "GOOGLE_OAUTH_CLIENT_SECRET=$(KV_REF google-oauth-client-secret)" \
        "STREAMLIT_COOKIE_SECRET=$(KV_REF streamlit-cookie-secret)" \
        "STORAGE_ACCOUNT_CONNECTION_STRING=$(KV_REF storage-connection-string)" \
        "STREAMLIT_ENV=prod" \
        "AUTH_USER_STORE=table" \
    --output none

# 7. Summary -----------------------------------------------------------------
echo "[7/7] done"
echo
echo "Auth provisioned. Bump streamlit >=1.42 and deploy:"
echo "    gh workflow run cd.yml --ref main"
