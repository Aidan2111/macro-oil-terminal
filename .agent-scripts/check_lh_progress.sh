#!/bin/zsh
ps -p 28402 -o pid,etime 2>/dev/null
echo "---"
echo "routes_completed=$(grep -c '^>>>' /tmp/lighthouse-v5.log)"
tail -3 /tmp/lighthouse-v5.log
echo "---fresh-jsons---"
find /Users/aidanbothost/Documents/macro_oil_terminal/docs/perf/lighthouse-wave4 -name '*.json' -newer /tmp/lighthouse-v5.bg.log 2>/dev/null | head
