"""Issue #100 — synthetic thesis monitor unit tests.

Acceptance criteria:
  * Pass path: a fixture SSE done payload that meets every contract
    field (>=3 instruments, exactly 5 checklist items, allowed
    stance, conviction 1-10) returns ok=True with no violations.
  * Fail path: each contract violation is detected individually.
  * 3-consecutive-failure streak counter works against the JSONL log.
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timedelta, timezone

import pytest

from backend.services.synthetic_monitor import (
    ALLOWED_STANCES,
    EXPECTED_CHECKLIST,
    LATENCY_SLA_SECONDS,
    MIN_INSTRUMENTS,
    SyntheticRun,
    consecutive_failures,
    recent_runs,
    record_synthetic_run,
    validate_done_event,
)


def _good_payload() -> dict:
    """A minimal-but-valid done event payload."""
    return {
        "thesis": {
            "instruments": [
                {"symbol": "CL=F"},
                {"symbol": "BZ=F"},
                {"symbol": "USO"},
            ],
            "checklist": [
                {"key": "stop_in_place"},
                {"key": "vol_clamp_ok"},
                {"key": "catalyst_clear"},
                {"key": "size_within_limit"},
                {"key": "thesis_understood"},
            ],
            "plain_english_headline": "Spread is stretched — short the spread.",
            "raw": {
                "stance": "short_spread",
                "conviction_0_to_10": 7,
                "plain_english_headline": "Spread is stretched — short the spread.",
            },
        }
    }


# ---------------------------------------------------------------------------
# Validation contract
# ---------------------------------------------------------------------------
def test_pass_path_returns_ok_with_no_violations():
    ok, violations = validate_done_event(_good_payload())
    assert ok is True
    assert violations == []


def test_too_few_instruments_fires_violation():
    p = _good_payload()
    p["thesis"]["instruments"] = [{"symbol": "CL=F"}, {"symbol": "BZ=F"}]
    ok, violations = validate_done_event(p)
    assert ok is False
    assert any("instruments has 2" in v for v in violations)


def test_wrong_checklist_count_fires_violation():
    p = _good_payload()
    # Drop the last item so checklist has 4.
    p["thesis"]["checklist"] = p["thesis"]["checklist"][:4]
    ok, violations = validate_done_event(p)
    assert ok is False
    assert any("checklist has 4" in v for v in violations)


def test_invalid_stance_fires_violation():
    p = _good_payload()
    p["thesis"]["raw"]["stance"] = "moonshot"
    ok, violations = validate_done_event(p)
    assert ok is False
    assert any("stance" in v for v in violations)


def test_conviction_out_of_range_fires_violation():
    p = _good_payload()
    p["thesis"]["raw"]["conviction_0_to_10"] = 11
    ok, violations = validate_done_event(p)
    assert ok is False
    assert any("conviction" in v for v in violations)


def test_conviction_non_numeric_fires_violation():
    p = _good_payload()
    p["thesis"]["raw"]["conviction_0_to_10"] = "high"
    ok, violations = validate_done_event(p)
    assert ok is False
    assert any("conviction_0_to_10 not numeric" in v for v in violations)


def test_null_headline_fires_violation():
    p = _good_payload()
    p["thesis"]["plain_english_headline"] = ""
    p["thesis"]["raw"]["plain_english_headline"] = ""
    ok, violations = validate_done_event(p)
    assert ok is False
    assert any("plain_english_headline" in v for v in violations)


def test_latency_sla_violation_when_duration_exceeds_threshold():
    p = _good_payload()
    ok, violations = validate_done_event(p, duration_s=LATENCY_SLA_SECONDS + 5)
    assert ok is False
    assert any("duration" in v and "SLA" in v for v in violations)


def test_latency_within_sla_does_not_violate():
    p = _good_payload()
    ok, violations = validate_done_event(p, duration_s=LATENCY_SLA_SECONDS - 5)
    assert ok is True
    assert violations == []


def test_non_dict_payload_fails_safely():
    ok, violations = validate_done_event("not a dict")
    assert ok is False
    assert violations == ["payload not a dict"]


# ---------------------------------------------------------------------------
# JSONL log + consecutive-failure streak
# ---------------------------------------------------------------------------
def test_record_and_recent_runs_roundtrip(tmp_path: pathlib.Path):
    log = tmp_path / "synthetic.jsonl"
    now = datetime.now(timezone.utc)
    runs = [
        SyntheticRun(
            started_at=(now - timedelta(minutes=15 * i)).isoformat(),
            finished_at=(now - timedelta(minutes=15 * i)).isoformat(),
            duration_s=42.0,
            ok=(i % 2 == 0),
            violations=([] if i % 2 == 0 else ["stance bad"]),
        )
        for i in range(5)
    ]
    for r in runs:
        record_synthetic_run(r, log_path=log)

    out = recent_runs(log_path=log)
    assert len(out) == 5
    # newest first
    assert out[0]["started_at"] >= out[-1]["started_at"]


def test_consecutive_failures_counts_trailing_run(tmp_path: pathlib.Path):
    log = tmp_path / "synthetic.jsonl"
    now = datetime.now(timezone.utc)
    # Order written: oldest -> newest. Newest 3 are failures.
    seq = [True, True, False, False, False]
    for i, ok in enumerate(seq):
        # Newer runs have NEWER timestamps, so iterate in time order.
        record_synthetic_run(
            SyntheticRun(
                started_at=(now + timedelta(minutes=i)).isoformat(),
                finished_at=(now + timedelta(minutes=i)).isoformat(),
                duration_s=10.0,
                ok=ok,
                violations=[] if ok else ["fail"],
            ),
            log_path=log,
        )
    streak = consecutive_failures(log_path=log)
    assert streak == 3, f"Expected streak=3, got {streak}"


def test_consecutive_failures_zero_when_latest_is_ok(tmp_path: pathlib.Path):
    log = tmp_path / "synthetic.jsonl"
    now = datetime.now(timezone.utc)
    record_synthetic_run(
        SyntheticRun(
            started_at=now.isoformat(),
            finished_at=now.isoformat(),
            duration_s=10.0,
            ok=True,
        ),
        log_path=log,
    )
    assert consecutive_failures(log_path=log) == 0


def test_recent_runs_handles_missing_log(tmp_path: pathlib.Path):
    log = tmp_path / "does-not-exist.jsonl"
    assert recent_runs(log_path=log) == []
    assert consecutive_failures(log_path=log) == 0


def test_log_prunes_entries_older_than_24h(tmp_path: pathlib.Path):
    log = tmp_path / "synthetic.jsonl"
    now = datetime.now(timezone.utc)
    # One ancient (48h ago) and one fresh.
    record_synthetic_run(
        SyntheticRun(
            started_at=(now - timedelta(hours=48)).isoformat(),
            finished_at=(now - timedelta(hours=48)).isoformat(),
            duration_s=10.0,
            ok=True,
        ),
        log_path=log,
    )
    record_synthetic_run(
        SyntheticRun(
            started_at=now.isoformat(),
            finished_at=now.isoformat(),
            duration_s=10.0,
            ok=True,
        ),
        log_path=log,
    )
    out = recent_runs(log_path=log)
    # Only the fresh run remains after pruning.
    assert len(out) == 1
    assert out[0]["started_at"].startswith(now.isoformat()[:13])


# ---------------------------------------------------------------------------
# Constants exposed for the GH workflow
# ---------------------------------------------------------------------------
def test_contract_constants_documented():
    assert ALLOWED_STANCES == ("long_spread", "short_spread", "flat")
    assert MIN_INSTRUMENTS == 3
    assert EXPECTED_CHECKLIST == 5
    assert LATENCY_SLA_SECONDS == 90.0
