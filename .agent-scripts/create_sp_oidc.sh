#!/bin/zsh
set -eu

APP_NAME="macro-oil-terminal-cd"
RG="oil-price-tracker"
SUB_ID=$(az account show --query id -o tsv)
TEN_ID=$(az account show --query tenantId -o tsv)

echo "=== Creating Entra app registration: $APP_NAME"
APP_ID=$(az ad app create --display-name "$APP_NAME" --query appId -o tsv)
echo "APP_ID=$APP_ID"

echo "=== Creating service principal backed by app"
az ad sp create --id "$APP_ID" --query id -o tsv > /tmp/sp_object_id.txt
SP_OBJECT_ID=$(cat /tmp/sp_object_id.txt)
echo "SP_OBJECT_ID=$SP_OBJECT_ID"

# Role assignment can take a moment for the SP to propagate.
echo "=== Waiting 10s for SP to propagate in directory"
sleep 10

echo "=== Assigning Contributor on RG $RG"
RG_SCOPE="/subscriptions/$SUB_ID/resourceGroups/$RG"
for attempt in 1 2 3 4 5; do
  if az role assignment create --assignee "$APP_ID" --role Contributor --scope "$RG_SCOPE" --output none 2>/tmp/role_err.txt; then
    echo "  role assigned on attempt $attempt"
    break
  fi
  echo "  attempt $attempt failed:"
  cat /tmp/role_err.txt | head -3
  sleep 10
done

echo "=== Adding federated credential (main branch)"
az ad app federated-credential create \
  --id "$APP_ID" \
  --parameters ~/Documents/macro_oil_terminal/.agent-scripts/federated_cred.json \
  --output none

echo "=== Adding federated credential (pull_request)"
az ad app federated-credential create \
  --id "$APP_ID" \
  --parameters ~/Documents/macro_oil_terminal/.agent-scripts/federated_cred_pr.json \
  --output none

echo "=== Saving IDs"
echo "$APP_ID" > ~/Documents/macro_oil_terminal/.agent-scripts/app_id.txt
echo "$TEN_ID" > ~/Documents/macro_oil_terminal/.agent-scripts/tenant_id.txt
echo "$SUB_ID" > ~/Documents/macro_oil_terminal/.agent-scripts/subscription_id.txt

echo "=== Verification"
echo "APP_ID=$APP_ID"
echo "TENANT_ID=$TEN_ID"
echo "SUBSCRIPTION_ID=$SUB_ID"
echo "Federated credentials:"
az ad app federated-credential list --id "$APP_ID" --query "[].{name:name, subject:subject}" -o table
echo "Role assignments:"
az role assignment list --assignee "$APP_ID" --query "[].{role:roleDefinitionName,scope:scope}" -o table
