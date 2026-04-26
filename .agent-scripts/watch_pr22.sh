#!/bin/zsh
export PATH="/Users/aidanbothost/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
cd /Users/aidanbothost/Documents/macro_oil_terminal
LOG=/tmp/pr22-watch.log
> $LOG
for i in $(seq 1 30); do
  ts=$(date -u +%H:%M:%S)
  st=$(gh pr view 22 --json statusCheckRollup --jq '.statusCheckRollup[] | select(.name == "Playwright end-to-end") | (.status + "|" + (.conclusion // "-"))')
  echo "$ts poll $i: $st" >> $LOG
  if [[ "$st" == *"COMPLETED"* ]]; then
    echo "$ts DONE" >> $LOG
    break
  fi
  sleep 30
done
