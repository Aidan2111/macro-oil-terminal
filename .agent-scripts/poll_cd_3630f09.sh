#!/bin/zsh
export PATH="/Users/aidanbothost/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
cd /Users/aidanbothost/Documents/macro_oil_terminal
sleep ${1:-0}
gh run list --branch main --limit 8 --json name,status,conclusion,headSha \
  --jq '.[] | select(.headSha | startswith("3630f09")) | (.name + "  " + .status + "  " + (.conclusion // "-"))'
