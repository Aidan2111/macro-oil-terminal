#!/usr/bin/env bash
#
# Reproduce the macro oil terminal stack from scratch (or update in place).
# Non-destructive by default: run `what-if` first, then the actual deploy.
#
# Usage:
#   ./infra/deploy.sh                 # full deploy
#   ./infra/deploy.sh --what-if       # preview only
#
# Idempotency: this script only creates the resource group + federated
# identity + CD secrets once; everything else (App Service, Web App,
# Azure OpenAI, Application Insights, alert rules, action group) is
# managed by Bicep and can be re-run safely.

set -euo pipefail

RG="${RG:-oil-price-tracker}"
LOCATION_PLAN="${LOCATION_PLAN:-westus2}"
LOCATION_OPENAI="${LOCATION_OPENAI:-eastus}"
ALERT_EMAIL="${ALERT_EMAIL:-$(az ad signed-in-user show --query mail -o tsv 2>/dev/null || az ad signed-in-user show --query userPrincipalName -o tsv)}"
BICEP_FILE="$(dirname "$0")/main.bicep"

WHAT_IF="${1:-}"

echo ">> Target: RG=$RG  plan=$LOCATION_PLAN  aoai=$LOCATION_OPENAI  alerts→$ALERT_EMAIL"

# ---- Resource group ----
if ! az group show -n "$RG" >/dev/null 2>&1; then
  echo ">> Creating resource group $RG in $LOCATION_PLAN"
  az group create -n "$RG" -l "$LOCATION_PLAN" --output none
else
  echo ">> RG $RG already exists (skipping create)"
fi

# ---- Bicep what-if preview ----
if [[ "$WHAT_IF" == "--what-if" ]]; then
  echo ">> what-if (no changes will be applied)"
  az deployment group what-if \
    --resource-group "$RG" \
    --template-file "$BICEP_FILE" \
    --parameters \
      planLocation="$LOCATION_PLAN" \
      openAiLocation="$LOCATION_OPENAI" \
      alertEmail="$ALERT_EMAIL"
  exit 0
fi

# ---- Deploy ----
echo ">> Deploying Bicep template"
DEPLOYMENT_NAME="oil-tracker-$(date -u +%Y%m%d%H%M%S)"
az deployment group create \
  --name "$DEPLOYMENT_NAME" \
  --resource-group "$RG" \
  --template-file "$BICEP_FILE" \
  --parameters \
    planLocation="$LOCATION_PLAN" \
    openAiLocation="$LOCATION_OPENAI" \
    alertEmail="$ALERT_EMAIL" \
  --output table

echo ""
echo ">> Outputs:"
az deployment group show \
  --resource-group "$RG" \
  --name "$DEPLOYMENT_NAME" \
  --query properties.outputs \
  --output json

cat <<NOTE

Next steps if you're bootstrapping from scratch:
  1. Create the CD service principal + federated credential:
       az ad app create --display-name macro-oil-terminal-cd
       (then az ad sp create, role assignment, federated-credential create)
     See .agent-scripts/create_sp_oidc.sh for the template.

  2. Set the three GitHub secrets:
       gh secret set AZURE_CLIENT_ID      -b <appId>
       gh secret set AZURE_TENANT_ID      -b <tenantId>
       gh secret set AZURE_SUBSCRIPTION_ID -b <subId>

  3. Push to main — CD will deploy the code onto the Web App.
NOTE
