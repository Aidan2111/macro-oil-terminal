#!/bin/zsh
# Wave 5 Lighthouse runner — captures the post-merge scores.
export PATH="/Users/aidanbothost/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
set -u
LOG=/tmp/lighthouse-v5.log
> $LOG
cd /Users/aidanbothost/Documents/macro_oil_terminal
echo "=== run start $(date -u +%FT%TZ) ===" >> $LOG
bash docs/perf/lighthouse-wave4/run.sh >> $LOG 2>&1
echo "=== run end $(date -u +%FT%TZ) ===" >> $LOG
