"""Summarise the latest swa diagnostic JSON in a glanceable way."""

from __future__ import annotations

import json
import sys


def main(path: str) -> int:
    with open(path) as f:
        d = json.load(f)
    for k, info in d.items():
        errors = info.get("errors", [])
        pageerrors = [e for e in errors if e["kind"] == "pageerror"]
        reqfails = [e for e in errors if e["kind"] == "reqfail"]
        consoleerr = [e for e in errors if e["kind"] == "console.error"]
        warnings = [e for e in errors if e["kind"] == "console.warning"]
        print(
            f"{k:18s} status={info.get('status'):>3} title={info.get('title','')!r:40s} "
            f"pageerr={len(pageerrors)} reqfail={len(reqfails)} "
            f"console.err={len(consoleerr)} warn={len(warnings)}"
        )
        for e in pageerrors:
            print("   PAGEERR:", e.get("msg", "")[:160])
        for e in reqfails:
            url = e.get("url", "")
            tail = "/".join(url.split("/")[-3:]) if url else ""
            print("   REQFAIL:", tail, e.get("failure", ""))
        for e in consoleerr:
            print("   CONSOLE.ERR:", e.get("text", "")[:160])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/swa_diag2.json"))
