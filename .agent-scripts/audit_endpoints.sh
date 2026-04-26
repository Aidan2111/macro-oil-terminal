#!/usr/bin/env bash
B=https://oil-tracker-api-canadaeast-0f18.azurewebsites.net
for route in /health /api/build-info /api/spread /api/inventory /api/cftc /api/positions /api/positions/account /api/positions/orders /api/fleet/snapshot /api/fleet/categories /api/thesis/latest /api/thesis/history; do
  body=$(curl -sS --max-time 30 "$B$route" 2>&1)
  src=$(echo "$body" | /usr/bin/python3 -c 'import sys,json
try:
  d=json.load(sys.stdin)
  print(d.get("source") or d.get("mode") or "-")
except Exception as e:
  print("ERR:", e)' 2>&1)
  echo "$route → $src"
done
echo --- backtest ---
curl -sS --max-time 60 -X POST -H 'Content-Type: application/json' -d '{}' "$B/api/backtest" | /usr/bin/python3 -c 'import sys,json
d=json.load(sys.stdin)
print("source",d.get("source","-"), "sharpe",d.get("sharpe"), "n_trades",d.get("n_trades"))'
