#!/bin/zsh
export PATH="/Users/aidanbothost/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
LOG=${1:-/tmp/foundry-thesis-test.log}
> $LOG
echo "=== start $(date -u +%FT%TZ) ===" >> $LOG
echo "--- /health ---" >> $LOG
curl -sS --max-time 30 https://oil-tracker-api-canadaeast-0f18.azurewebsites.net/health >> $LOG 2>&1
echo >> $LOG
echo "--- /api/build-info ---" >> $LOG
curl -sS --max-time 30 https://oil-tracker-api-canadaeast-0f18.azurewebsites.net/api/build-info >> $LOG 2>&1
echo >> $LOG
echo "--- /api/thesis/generate (deep, SSE first 60 lines) ---" >> $LOG
START=$(date +%s)
curl -sS -N --max-time 120 -X POST -H 'Content-Type: application/json' -d '{"mode":"deep"}' \
  https://oil-tracker-api-canadaeast-0f18.azurewebsites.net/api/thesis/generate 2>&1 | head -60 >> $LOG
END=$(date +%s)
echo >> $LOG
echo "--- elapsed: $((END-START))s ---" >> $LOG
echo "=== end $(date -u +%FT%TZ) ===" >> $LOG
