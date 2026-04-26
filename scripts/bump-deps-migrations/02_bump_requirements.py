#!/usr/bin/env python3
"""Apply the coordinated dep bumps to ``requirements.txt`` and ``backend/requirements.txt``.

Idempotent — uses literal-line replacement keyed on the package prefix, so re-runs
that find the new pin already in place are no-ops.

We deliberately do NOT bump:
- ``openai``  — the Foundry path uses ``client.beta.assistants/threads`` heavily
  (backend/services/trade_thesis_foundry.py) and that surface is removed in
  openai 2.x. Out of scope for this batch.
- ``azure-ai-projects`` / ``azure-identity`` — just bumped, leave as-is.
- ``streamlit`` / ``plotly`` / ``azure-monitor-opentelemetry`` / ``azure-data-tables``
  — root requirements stack stays on its current pins until the Streamlit
  teardown (separate PR) lands.
- ``yfinance`` — the major bump 0.2 -> 1.3 pulls in ``curl_cffi``, ``peewee``,
  ``protobuf`` and tightens the API; the existing call sites already pass
  ``auto_adjust=False`` explicitly so we *could* try, but we leave it to a
  follow-up PR to avoid blocking the numpy/pandas/sklearn/arch/statsmodels
  bumps that are the real point of this exercise.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# package -> new pin string (full RHS of the requirement line)
BUMPS = {
    "numpy": "numpy>=2.4.4",
    "pandas": "pandas>=3.0.2",
    "scikit-learn": "scikit-learn>=1.8.0",
    "arch": "arch>=8.0.0",
    "statsmodels": "statsmodels>=0.14.6",
}


def _bump(p: Path) -> int:
    if not p.exists():
        return 0
    lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
    n = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Match "<pkg>" up to the first comparator/bracket — that's the package name
        m = re.match(r"^([A-Za-z0-9_.\-]+)", stripped)
        if not m:
            continue
        pkg = m.group(1).lower()
        if pkg in BUMPS:
            new = BUMPS[pkg]
            # preserve trailing newline
            tail = "\n" if line.endswith("\n") else ""
            new_line = new + tail
            if line != new_line:
                lines[i] = new_line
                n += 1
    if n:
        p.write_text("".join(lines), encoding="utf-8")
    return n


def main() -> int:
    total = 0
    for rel in ("requirements.txt", "backend/requirements.txt"):
        p = REPO / rel
        n = _bump(p)
        print(f"  {rel}: {n} pin(s) updated")
        total += n
    print(f"\nTotal pin updates: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
