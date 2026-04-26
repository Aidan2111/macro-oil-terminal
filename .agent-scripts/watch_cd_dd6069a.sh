#!/bin/zsh
export PATH="/Users/aidanbothost/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
cd /Users/aidanbothost/Documents/macro_oil_terminal
LOG=/tmp/cd-dd6069a.log
> $LOG
for i in $(seq 1 25); do
  ts=$(date -u +%H:%M:%S)
  st=$(gh run list --branch main --limit 8 --json name,status,conclusion,headSha --jq '.[] | select(.headSha | startswith("dd6069a")) | (.name + "|" + .status + "|" + (.conclusion // "-"))')
  echo "$ts poll $i:" >> $LOG
  echo "$st" >> $LOG
  pending=$(gh run list --branch main --limit 8 --json status,conclusion,headSha,name --jq '[.[] | select(.headSha | startswith("dd6069a")) | select(.name | startswith("CD")) | .status] | map(select(. != "completed")) | length')
  echo "cd_pending=$pending" >> $LOG
  if [ "$pending" = "0" ] && [ -n "$st" ]; then
    echo "$ts CD_DONE" >> $LOG
    break
  fi
  sleep 30
done
