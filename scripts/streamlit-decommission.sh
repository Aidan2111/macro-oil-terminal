#!/usr/bin/env bash
# ===========================================================================
# Streamlit Azure decommission — DO NOT RUN BEFORE 2026-04-27 04:00 UTC.
#
# This script tears down the legacy Streamlit Azure web app + plan after
# the 48h-stable rollback window closes. It is a one-shot, manual run —
# Aidan triggers it from his workstation once the React stack at
# https://delightful-pebble-00d8eb30f.7.azurestaticapps.net/ has been
# stable for 48 consecutive hours and nothing in the keep-warm / CD
# pipelines is pinging the Streamlit URL.
#
# Pre-flight gates inside the script:
#   1. React SWA must return 2xx on /
#   2. FastAPI backend must return 2xx on /health
#   3. Caller must pass --i-have-confirmed-window-passed explicitly
#
# Usage:
#   ./scripts/streamlit-decommission.sh --i-have-confirmed-window-passed
#
# Roll-forward only: the App Service plan deletion is irreversible.
# ===========================================================================

set -euo pipefail

[ "${1:-}" = "--i-have-confirmed-window-passed" ] || {
  echo "ERROR: pass --i-have-confirmed-window-passed explicitly." >&2
  echo "Window opens 2026-04-27 04:00 UTC. Do not run before then." >&2
  exit 1
}

RG="oil-price-tracker"
STREAMLIT_APP="oil-tracker-app-canadaeast-4474"
STREAMLIT_PLAN="oil-tracker-canadaeast-plan"
REACT_SWA_URL="https://delightful-pebble-00d8eb30f.7.azurestaticapps.net/"
API_URL="https://oil-tracker-api-canadaeast-0f18.azurewebsites.net/health"

echo "==> Pre-flight: confirm React stack still green"
echo "  React SWA: $REACT_SWA_URL"
curl -fI "$REACT_SWA_URL" > /dev/null || {
  echo "REACT_DOWN: aborting Streamlit decommission" >&2
  exit 1
}
echo "  -> React SWA reachable."

echo "  FastAPI backend: $API_URL"
curl -fI "$API_URL" > /dev/null || {
  echo "API_DOWN: aborting Streamlit decommission" >&2
  exit 1
}
echo "  -> FastAPI backend reachable."

echo
echo "==> Deleting Streamlit web app: $STREAMLIT_APP"
az webapp delete -g "$RG" -n "$STREAMLIT_APP" --keep-empty-plan
echo "  -> Web app deleted (plan kept for safety check)."

echo
echo "==> Checking App Service plan site count: $STREAMLIT_PLAN"
SITES=$(az appservice plan show -g "$RG" -n "$STREAMLIT_PLAN" --query 'numberOfSites' -o tsv 2>/dev/null || echo "missing")
echo "  numberOfSites=$SITES"

if [ "$SITES" = "0" ]; then
  echo "==> Plan is empty — deleting: $STREAMLIT_PLAN"
  az appservice plan delete -g "$RG" -n "$STREAMLIT_PLAN" --yes
  echo "  -> Plan deleted."
elif [ "$SITES" = "missing" ]; then
  echo "  Plan already gone — nothing to delete."
else
  echo "  WARNING: plan still has $SITES site(s); leaving it in place."
  echo "  Inspect with: az webapp list -g $RG --query \"[?appServicePlanId | contains(@, '$STREAMLIT_PLAN')]\" -o table"
fi

echo
echo "==> Logging westus2 leftovers (likely empty by now):"
az webapp list -g "$RG" --query "[?contains(name, 'westus2')]" -o table || true

echo
echo "==> Streamlit decommission complete. React + FastAPI continue serving."
