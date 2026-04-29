#!/bin/zsh
export PATH="/Users/aidanbothost/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
cd /Users/aidanbothost/Documents/macro_oil_terminal
PR=$1
LOG=/tmp/pr$PR-status.log
> $LOG
for i in $(seq 1 30); do
  ts=$(date -u +%H:%M:%S)
  pending=$(gh pr view $PR --json statusCheckRollup --jq '[.statusCheckRollup[] | select(.status != "COMPLETED")] | length')
  failed=$(gh pr view $PR --json statusCheckRollup --jq '[.statusCheckRollup[] | select(.conclusion == "FAILURE")] | length')
  echo "$ts pending=$pending failed=$failed" >> $LOG
  if [ "$pending" = "0" ]; then echo "$ts DONE failed=$failed" >> $LOG; break; fi
  sleep 30
done
