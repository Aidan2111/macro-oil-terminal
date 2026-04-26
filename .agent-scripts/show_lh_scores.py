#!/usr/bin/env python3
import json, glob, os
os.chdir('/Users/aidanbothost/Documents/macro_oil_terminal/docs/perf/lighthouse-wave4')
for f in sorted(glob.glob('*.json')):
    try:
        j = json.load(open(f))
        c = j.get('categories', {})
        def s(k): return round((c.get(k, {}).get('score') or 0) * 100)
        print(f"{f:<32} perf={s('performance')} a11y={s('accessibility')} bp={s('best-practices')} seo={s('seo')}")
    except Exception as e:
        print(f, 'err:', e)
