#!/bin/zsh
cd /Users/aidanbothost/Documents/macro_oil_terminal/docs/perf/lighthouse-wave4
for f in *.json; do
  /usr/bin/python3 -c "
import json, sys
try:
    j = json.load(open('$f'))
    c = j.get('categories', {})
    def s(k): return round((c.get(k, {}).get('score') or 0) * 100)
    print(f'{\"'$f'\":<30}', 'perf=' + str(s('performance')), 'a11y=' + str(s('accessibility')), 'bp=' + str(s('best-practices')), 'seo=' + str(s('seo')))
except Exception as e:
    print('$f', 'err:', e)
" 2>&1
done
