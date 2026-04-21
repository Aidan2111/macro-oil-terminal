#!/bin/zsh
set -u
keep="oil-tracker-plan-westus2"
for region in centralus westus3 westeurope canadacentral francecentral; do
  plan="oil-tracker-plan-$region"
  echo "Deleting $plan..."
  az appservice plan delete --resource-group oil-price-tracker --name "$plan" --yes --output none 2>&1 | head -3
done
echo "=== Remaining plans ==="
az appservice plan list --resource-group oil-price-tracker --output table 2>&1
