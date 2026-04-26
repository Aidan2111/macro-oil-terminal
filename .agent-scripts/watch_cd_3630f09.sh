#!/bin/zsh
# Polls CD status every 30s up to 15 mins, writes status to /tmp/cd-3630f09.log
export PATH="/Users/aidanbothost/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
cd /Users/aidanbothost/Documents/macro_oil_terminal
LOG=/tmp/cd-3630f09.log
> $LOG
for i in $(seq 1 30); do
  echo "=== $(date -u +%H:%M:%S) poll $i ===" >> $LOG
  gh run list --branch main --limit 8 --json name,status,conclusion,headSha \
    --jq '.[] | select(.headSha | startswith("3630f09")) | (.name + "  " + .status + "  " + (.conclusion // "-"))' >> $LOG 2>&1
  pending=$(gh run list --branch main --limit 8 --json status,headSha \
    --jq '[.[] | select(.headSha | startswith("3630f09")) | .status] | map(select(. != "completed")) | length')
  echo "pending=$pending" >> $LOG
  if [ "$pending" = "0" ]; then echo "ALL_DONE" >> $LOG; break; fi
  sleep 30
done
