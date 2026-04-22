#!/bin/zsh
set -eu

RG=oil-price-tracker
APP=$(cat ~/Documents/macro_oil_terminal/.agent-scripts/app_name.txt)
SUB=$(cat ~/Documents/macro_oil_terminal/.agent-scripts/subscription_id.txt)
MAIL=$(az ad signed-in-user show --query mail -o tsv 2>/dev/null || az ad signed-in-user show --query userPrincipalName -o tsv)
echo "APP=$APP  MAIL=$MAIL"

APP_RID="/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.Web/sites/$APP"

# ----- Action group (email target) -----
echo "--- action group"
az monitor action-group create \
  --resource-group "$RG" \
  --name "oil-tracker-alerts" \
  --short-name "oilalrt" \
  --action email "aidan-alert" "$MAIL" \
  --output none

AG_RID="/subscriptions/$SUB/resourceGroups/$RG/providers/microsoft.insights/actionGroups/oil-tracker-alerts"

# ----- Alert 1: HTTP 5xx > 5 in 5m -----
echo "--- alert: http 5xx > 5 in 5m"
az monitor metrics alert create \
  --name "oil-tracker-http5xx" \
  --resource-group "$RG" \
  --scopes "$APP_RID" \
  --condition "total Http5xx > 5" \
  --window-size 5m \
  --evaluation-frequency 1m \
  --severity 2 \
  --description "HTTP 5xx responses > 5 in any 5-minute window" \
  --action "$AG_RID" \
  --output none

# ----- Alert 2: HttpResponseTime avg > 5s over 5m -----
echo "--- alert: slow response avg > 5s"
az monitor metrics alert create \
  --name "oil-tracker-slow-response" \
  --resource-group "$RG" \
  --scopes "$APP_RID" \
  --condition "avg HttpResponseTime > 5" \
  --window-size 5m \
  --evaluation-frequency 1m \
  --severity 3 \
  --description "Average HTTP response time > 5s over 5 minutes" \
  --action "$AG_RID" \
  --output none

echo "--- alerts created"
az monitor metrics alert list --resource-group "$RG" --query "[].{name:name, severity:severity, enabled:enabled}" -o table
echo "--- action group"
az monitor action-group show --resource-group "$RG" --name oil-tracker-alerts --query "{name:name,emailReceivers:emailReceivers[].emailAddress}" -o json
