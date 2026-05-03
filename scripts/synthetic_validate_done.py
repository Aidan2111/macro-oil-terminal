#!/usr/bin/env python3
"""Standalone validator used by the synthetic-thesis-monitor cron.

Mirrors backend.services.synthetic_monitor.validate_done_event but
imports nothing from the repo so the GH Actions runner doesn't need
the full backend install path. Stdlib only.

Usage:
    python3 scripts/synthetic_validate_done.py <done_payload_json> <duration_s>

Outputs JSON {ok, violations, stance, conviction} on stdout.
"""

from __future__ import annotations

import json
import sys


def validate(payload: dict, duration_s: float) -> dict:
    violations: list[str] = []
    if not isinstance(payload, dict):
        return {"ok": False, "violations": ["payload not a dict"], "stance": None, "conviction": None}

    thesis = payload.get("thesis") or {}
    if not isinstance(thesis, dict):
        return {"ok": False, "violations": ["thesis missing or not a dict"], "stance": None, "conviction": None}

    instr = thesis.get("instruments") or []
    if not isinstance(instr, list) or len(instr) < 3:
        violations.append(f"instruments has {len(instr) if isinstance(instr, list) else 'N/A'} entries, expected >= 3")

    chk = thesis.get("checklist") or []
    if not isinstance(chk, list) or len(chk) != 5:
        violations.append(f"checklist has {len(chk) if isinstance(chk, list) else 'N/A'} entries, expected exactly 5")

    raw = thesis.get("raw") or {}
    if not isinstance(raw, dict):
        raw = {}
    stance = raw.get("stance")
    if stance not in ("long_spread", "short_spread", "flat"):
        violations.append(f"stance {stance!r} not in allowed set")

    conv = raw.get("conviction_0_to_10")
    if not isinstance(conv, (int, float)):
        violations.append(f"conviction_0_to_10 not numeric (got {type(conv).__name__})")
    else:
        c = int(conv)
        if c < 1 or c > 10:
            violations.append(f"conviction_0_to_10={conv} not in 1..10")

    headline = thesis.get("plain_english_headline") or raw.get("plain_english_headline")
    if not headline:
        violations.append("plain_english_headline empty")

    if duration_s > 90.0:
        violations.append(f"duration {duration_s:.1f}s exceeds 90s SLA")

    return {
        "ok": not violations,
        "violations": violations,
        "stance": stance if stance in ("long_spread", "short_spread", "flat") else None,
        "conviction": conv if isinstance(conv, (int, float)) else None,
    }


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(json.dumps({"ok": False, "violations": ["script invoked with wrong arity"], "stance": None, "conviction": None}))
        return 0
    try:
        payload = json.loads(argv[1])
    except Exception as exc:
        print(json.dumps({"ok": False, "violations": [f"payload not parseable: {exc!r}"], "stance": None, "conviction": None}))
        return 0
    try:
        duration_s = float(argv[2])
    except Exception:
        duration_s = 0.0
    print(json.dumps(validate(payload, duration_s)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
