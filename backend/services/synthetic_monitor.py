"""Synthetic transaction monitor — issue #100.

`/api/data-quality` tells us the read path is alive. The write path —
Foundry SSE thesis generation — is the more failure-prone surface
(LLM timeouts, App Service idle hangs, audit-log writes). Nothing
exercises that surface on a schedule.

This module provides:

  * :func:`validate_done_event` — pure function that checks an SSE
    `done` event payload against the issue-#100 contract:
       - instruments[] has at least 3 entries
       - checklist[] has exactly 5 entries
       - raw.stance ∈ {long_spread, short_spread, flat}
       - raw.conviction_0_to_10 is int 1..10
       - none of the required fields are None
  * :func:`record_synthetic_run` / :func:`recent_runs` — a
    24h ring-buffer of recent runs persisted to
    `data/synthetic_thesis_runs.jsonl`. Powers the
    /api/synthetic/last-24h inspection endpoint.

The cron itself lives in `.github/workflows/synthetic-thesis-monitor.yml`
and POSTs runs back to a dedicated route.
"""

from __future__ import annotations

import json
import os
import pathlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


# Validation contract — exposed for tests to import.
ALLOWED_STANCES = ("long_spread", "short_spread", "flat")
MIN_INSTRUMENTS = 3
EXPECTED_CHECKLIST = 5
LATENCY_SLA_SECONDS = 90.0


# Persistence — 24h ring buffer of run summaries. Lives next to the
# audit log so ops tooling can sweep both at once.
_LOG_PATH = pathlib.Path(
    os.environ.get(
        "SYNTHETIC_RUN_LOG",
        str(pathlib.Path(__file__).resolve().parents[2] / "data" / "synthetic_thesis_runs.jsonl"),
    )
)
_RETENTION_HOURS = 24.0


@dataclass
class SyntheticRun:
    """One end-to-end synthetic thesis check."""

    started_at: str            # ISO-8601 UTC
    finished_at: str           # ISO-8601 UTC
    duration_s: float          # wall clock
    ok: bool                   # all validators passed AND completed in time
    violations: list[str] = field(default_factory=list)
    latency_violation: bool = False
    stance: str | None = None
    conviction: int | None = None
    notes: str | None = None   # arbitrary debug notes from the cron


def validate_done_event(payload: Any, *, duration_s: float | None = None) -> tuple[bool, list[str]]:
    """Issue #100 contract on the SSE `done` event.

    Returns ``(ok, violations)``. ``ok`` is True iff every check passed.
    ``violations`` lists every contract failure.

    ``duration_s`` is optional; supply when the caller wants the
    latency SLA (90s) folded into the verdict. The latency check is
    additive — pass it separately if you'd rather track it as a
    separate signal.
    """
    violations: list[str] = []
    if not isinstance(payload, dict):
        return False, ["payload not a dict"]

    thesis = payload.get("thesis") or {}
    if not isinstance(thesis, dict):
        return False, ["thesis missing or not a dict"]

    # instruments
    instruments = thesis.get("instruments") or []
    if not isinstance(instruments, list):
        violations.append("instruments not a list")
    elif len(instruments) < MIN_INSTRUMENTS:
        violations.append(f"instruments has {len(instruments)} entries, expected >= {MIN_INSTRUMENTS}")

    # checklist
    checklist = thesis.get("checklist") or []
    if not isinstance(checklist, list):
        violations.append("checklist not a list")
    elif len(checklist) != EXPECTED_CHECKLIST:
        violations.append(f"checklist has {len(checklist)} entries, expected exactly {EXPECTED_CHECKLIST}")

    # raw.stance
    raw = thesis.get("raw") or {}
    if not isinstance(raw, dict):
        violations.append("raw missing or not a dict")
        raw = {}
    stance = raw.get("stance")
    if stance not in ALLOWED_STANCES:
        violations.append(f"stance {stance!r} not in {ALLOWED_STANCES}")

    # raw.conviction_0_to_10
    conv = raw.get("conviction_0_to_10")
    if not isinstance(conv, (int, float)):
        violations.append(f"conviction_0_to_10 not numeric (got {type(conv).__name__})")
    else:
        conv_int = int(conv)
        if conv_int < 1 or conv_int > 10:
            violations.append(f"conviction_0_to_10={conv} not in 1..10")

    # No-null check on required scalars in raw + thesis. We deliberately
    # don't recurse into instruments/checklist (those are validated by
    # length above and have their own optional-field allowances).
    required_scalars = (
        ("plain_english_headline", thesis.get("plain_english_headline") or raw.get("plain_english_headline")),
        ("stance", stance),
        ("conviction_0_to_10", conv),
    )
    for name, val in required_scalars:
        if val is None or (isinstance(val, str) and not val.strip()):
            violations.append(f"required field {name!r} is null/empty")

    # Latency SLA, if requested.
    if duration_s is not None and duration_s > LATENCY_SLA_SECONDS:
        violations.append(f"duration {duration_s:.1f}s exceeds {LATENCY_SLA_SECONDS}s SLA")

    return (len(violations) == 0), violations


def record_synthetic_run(run: SyntheticRun, *, log_path: pathlib.Path | None = None) -> None:
    """Append a run record to the JSONL log, then prune entries older
    than 24h. Best-effort — errors are swallowed (the cron must never
    fail because of logging)."""
    path = log_path or _LOG_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(run), default=str) + "\n")
        _prune_old(path)
    except Exception:  # pragma: no cover — disk failures must not break the cron
        pass


def _prune_old(path: pathlib.Path) -> None:
    """Drop log entries older than the retention window. Rewrites the
    file in place; small (≤ ~96 entries / day) so this is fine."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=_RETENTION_HOURS)
        kept: list[str] = []
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    ts = rec.get("started_at")
                    if isinstance(ts, str):
                        when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        if when.tzinfo is None:
                            when = when.replace(tzinfo=timezone.utc)
                        if when < cutoff:
                            continue
                    kept.append(line)
                except Exception:
                    # Malformed line — keep it so we can debug, but don't crash.
                    kept.append(line)
        with open(path, "w", encoding="utf-8") as fh:
            for line in kept:
                fh.write(line + "\n")
    except FileNotFoundError:
        return


def recent_runs(*, log_path: pathlib.Path | None = None, limit: int = 100) -> list[dict]:
    """Return the most-recent runs (newest first), up to ``limit``."""
    path = log_path or _LOG_PATH
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = [ln.rstrip("\n") for ln in fh if ln.strip()]
    except FileNotFoundError:
        return []
    runs: list[dict] = []
    for ln in lines:
        try:
            runs.append(json.loads(ln))
        except Exception:
            continue
    runs.sort(key=lambda r: r.get("started_at") or "", reverse=True)
    return runs[:limit]


def consecutive_failures(*, log_path: pathlib.Path | None = None) -> int:
    """Count the trailing run of failed checks (newest backwards).

    Used by the workflow to decide whether to escalate to a paging
    comment after 3 consecutive failures.
    """
    runs = recent_runs(log_path=log_path)
    streak = 0
    for r in runs:
        if r.get("ok"):
            break
        streak += 1
    return streak


__all__ = [
    "ALLOWED_STANCES",
    "MIN_INSTRUMENTS",
    "EXPECTED_CHECKLIST",
    "LATENCY_SLA_SECONDS",
    "SyntheticRun",
    "validate_done_event",
    "record_synthetic_run",
    "recent_runs",
    "consecutive_failures",
]
