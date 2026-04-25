#!/bin/bash
RUN_ID="${1:-24922280739}"
for i in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  S=$(/Users/aidanbothost/.local/bin/gh run view "$RUN_ID" --repo Aidan2111/macro-oil-terminal --json status,conclusion -q '.status+":"+.conclusion')
  echo "attempt $i: $S"
  if echo "$S" | grep -q "completed"; then
    break
  fi
  sleep 20
done
echo "FINAL: $S"
