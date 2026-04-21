#!/bin/zsh
set -u
regions=(westus2 centralus westus3 northeurope westeurope uksouth canadacentral francecentral)
for region in "${regions[@]}"; do
  echo "=== $region ==="
  az appservice plan create \
    --name "oil-tracker-plan-$region" \
    --resource-group oil-price-tracker \
    --sku F1 \
    --is-linux \
    --location "$region" \
    --output none 2>&1 | head -5
  rc=$?
  echo "  exit=$rc"
done
