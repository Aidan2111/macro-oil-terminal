#!/bin/zsh
export PATH="/Users/aidanbothost/.local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
LOG=/tmp/foundry-retry-tail.log
> $LOG

# Start log tail in background
nohup az webapp log tail -g oil-price-tracker -n oil-tracker-api-canadaeast-0f18 \
  --provider application > /tmp/foundry-retry-tail.raw 2>&1 &
TAIL_PID=$!
echo "tail_pid=$TAIL_PID" >> $LOG
sleep 3

# Flip USE_FOUNDRY=true + restart
echo "=== set USE_FOUNDRY=true $(date -u +%FT%TZ) ===" >> $LOG
az webapp config appsettings set -g oil-price-tracker -n oil-tracker-api-canadaeast-0f18 \
  --settings USE_FOUNDRY=true -o tsv 2>&1 | tail -3 >> $LOG
echo "=== restart $(date -u +%FT%TZ) ===" >> $LOG
az webapp restart -g oil-price-tracker -n oil-tracker-api-canadaeast-0f18 >> $LOG 2>&1
sleep 35

# Hit /health to warm container
echo "=== warm-up health $(date -u +%FT%TZ) ===" >> $LOG
curl -sS --max-time 20 https://oil-tracker-api-canadaeast-0f18.azurewebsites.net/health >> $LOG 2>&1
echo "" >> $LOG

# Trigger thesis generation, capture full SSE
echo "=== thesis fast $(date -u +%FT%TZ) ===" >> $LOG
START=$(date +%s)
curl -sS -N --max-time 180 -X POST -H 'Content-Type: application/json' -d '{"mode":"fast"}' \
  https://oil-tracker-api-canadaeast-0f18.azurewebsites.net/api/thesis/generate >> $LOG 2>&1
END=$(date +%s)
echo "" >> $LOG
echo "=== elapsed: $((END-START))s ===" >> $LOG

# Wait a bit for log tail to flush, then kill
sleep 8
kill $TAIL_PID 2>/dev/null

# Check what got persisted
echo "=== /api/thesis/latest $(date -u +%FT%TZ) ===" >> $LOG
curl -sS --max-time 10 https://oil-tracker-api-canadaeast-0f18.azurewebsites.net/api/thesis/latest >> $LOG 2>&1
echo "" >> $LOG

echo "=== app log tail (last 200 lines) ===" >> $LOG
tail -200 /tmp/foundry-retry-tail.raw >> $LOG

# Final: rollback to safe state regardless of outcome
echo "=== ROLLBACK USE_FOUNDRY=false $(date -u +%FT%TZ) ===" >> $LOG
az webapp config appsettings set -g oil-price-tracker -n oil-tracker-api-canadaeast-0f18 \
  --settings USE_FOUNDRY=false -o tsv 2>&1 | tail -3 >> $LOG
az webapp restart -g oil-price-tracker -n oil-tracker-api-canadaeast-0f18 >> $LOG 2>&1
echo "=== done $(date -u +%FT%TZ) ===" >> $LOG
