#!/usr/bin/env python3
"""Apply pandas-3 / numpy-2.4 / Python-3.13-friendly migrations across the repo.

Idempotent: each rewrite is a literal-string replace that becomes a no-op once
applied. Safe to run multiple times.

What it changes
---------------
1. ``pd.Timestamp.utcnow()``        -> ``pd.Timestamp.now(tz="UTC").tz_convert(None)``
   (pandas 3.0 removed ``Timestamp.utcnow``; we keep naive-UTC semantics so
   downstream ``.strftime`` / fetched_at consumers don't see tz suffixes.)
2. ``pd.Timestamp.utcnow().tz_localize(None)`` collapses too — the explicit
   ``.tz_localize(None)`` guard in thesis_context.py is now redundant because
   ``tz_convert(None)`` already strips. We rewrite it to the exact same
   ``pd.Timestamp.now(tz="UTC").tz_convert(None)`` form (the duplicate
   ``.tz_localize(None)`` would otherwise raise ``TypeError`` on naive ts).
3. ``pd.Timestamp.utcfromtimestamp(x)`` -> ``pd.Timestamp.fromtimestamp(x, tz="UTC").tz_convert(None)``
4. ``datetime.utcnow()``            -> ``datetime.now(timezone.utc).replace(tzinfo=None)``
   plus, on first hit, rewrites ``from datetime import datetime, timedelta`` to
   include ``timezone`` so the new code resolves.

We deliberately *do not* touch:
- backend/main.py — its ``_utcnow_iso`` helper already uses ``datetime.now(UTC)``
  internally; nothing to change.
- yfinance call sites — the existing code already passes ``auto_adjust=False``
  explicitly, so the yfinance 1.0 default flip is a no-op.
- openai usage — we are NOT bumping openai in this batch (see PR body).

Usage
-----
    python scripts/bump-deps-migrations/01_apply_python_migrations.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _replace(p: Path, old: str, new: str) -> int:
    if not p.exists():
        return 0
    src = p.read_text(encoding="utf-8")
    if old not in src:
        return 0
    out = src.replace(old, new)
    p.write_text(out, encoding="utf-8")
    return src.count(old)


def _ensure_timezone_import(p: Path) -> bool:
    """Make sure ``timezone`` is imported alongside ``datetime`` in *p*.

    Idempotent — returns True if it actually edited the file.
    """
    if not p.exists():
        return False
    src = p.read_text(encoding="utf-8")
    target = "from datetime import datetime, timedelta"
    replacement = "from datetime import datetime, timedelta, timezone"
    if target in src and "timezone" not in src.split("\n", 50)[0:50][0:50]:
        # naive scan: only patch if "timezone" is not already in the file's import region
        head = "\n".join(src.splitlines()[:30])
        if "timezone" not in head:
            src = src.replace(target, replacement, 1)
            p.write_text(src, encoding="utf-8")
            return True
    return False


def main() -> int:
    total = 0

    # --- 1. pd.Timestamp.utcnow() (and the .tz_localize(None) flavour) ----
    pd_targets = [
        "providers/inventory.py",
        "providers/_cftc.py",
        "providers/pricing.py",
        "thesis_context.py",
        "data_ingestion.py",
        "app.py",
        "tests/unit/test_coverage_gaps.py",
        "tests/unit/test_thesis_context_full.py",
        "tests/unit/test_cftc_integration.py",
    ]
    for rel in pd_targets:
        p = REPO / rel
        # Order matters: rewrite the longer form first so we don't double-replace.
        n = _replace(
            p,
            "pd.Timestamp.utcnow().tz_localize(None)",
            'pd.Timestamp.now(tz="UTC").tz_convert(None)',
        )
        n += _replace(
            p,
            "pd.Timestamp.utcnow()",
            'pd.Timestamp.now(tz="UTC").tz_convert(None)',
        )
        if n:
            print(f"  [pd.utcnow]      {rel}: {n} site(s)")
            total += n

    # --- 2. pd.Timestamp.utcfromtimestamp(x) ------------------------------
    for rel in ["providers/_cftc.py"]:
        p = REPO / rel
        n = _replace(
            p,
            "pd.Timestamp.utcfromtimestamp(hit[0])",
            'pd.Timestamp.fromtimestamp(hit[0], tz="UTC").tz_convert(None)',
        )
        if n:
            print(f"  [pd.utcfromts]   {rel}: {n} site(s)")
            total += n

    # --- 3. datetime.utcnow() (Python 3.13 deprecation) -------------------
    dt_targets = ["crack_spread.py", "providers/_polygon.py", "providers/_yfinance.py"]
    for rel in dt_targets:
        p = REPO / rel
        if not p.exists():
            continue
        # add timezone import first
        _ensure_timezone_import(p)
        # then rewrite the call
        n = _replace(
            p,
            "datetime.utcnow()",
            "datetime.now(timezone.utc).replace(tzinfo=None)",
        )
        if n:
            print(f"  [dt.utcnow]      {rel}: {n} site(s)")
            total += n

    print(f"\nTotal rewrites: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
