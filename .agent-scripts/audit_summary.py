"""Print a glanceable summary of visual-audit findings."""

from __future__ import annotations

import glob
import json


for path in sorted(glob.glob("/tmp/visual-audit/findings_*.json")):
    rows = json.load(open(path))
    for row in rows:
        scroll = row.get("horizScroll")
        ovf = row.get("overflowing", []) or []
        taps = row.get("tinyTaps", []) or []
        tiny = row.get("tinyFontCount", 0) or 0
        flag = scroll or len(ovf) > 0 or len(taps) > 0
        marker = "!!" if flag else "  "
        vp = row["viewport"]
        route = row["route"]
        print(
            f"{marker} {vp:9s} {route:18s} scroll={scroll} ovf={len(ovf)} taps={len(taps)} tiny={tiny}"
        )
        if ovf:
            for e in ovf[:2]:
                print(f"     ovf: {e['tag']} w={e['w']} cls={e['cls'][:60]}")
        if taps:
            for e in taps[:2]:
                print(
                    f"     tap: {e['tag']} {e['w']}x{e['h']} text={e['text'][:30]!r}"
                )
