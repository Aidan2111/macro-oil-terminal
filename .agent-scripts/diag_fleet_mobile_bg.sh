#!/bin/zsh
export PATH="/Users/aidanbothost/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
cd /Users/aidanbothost/Documents/macro_oil_terminal
source .venv/bin/activate
OUT=${1:-/tmp/fleet-mobile-current.png}
LOG=${2:-/tmp/fleet-mobile-diag.log}
> $LOG
echo "=== start $(date -u +%FT%TZ) ===" >> $LOG
python3 "/Users/aidanbothost/Library/Application Support/Claude/local-agent-mode-sessions/5067c16f-89e7-4699-bede-51138f103f3e/c8d98b10-d3b3-496e-a9ad-3e0e8d45a6f4/local_a2bee47f-7fac-40b6-be96-efbaaf04fd74/outputs/diag_fleet_mobile.py" "$OUT" >> $LOG 2>&1
echo "=== end $(date -u +%FT%TZ) ===" >> $LOG
