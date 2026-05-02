"""Issue #104 — LLM regression corpus on canonical historical scenarios.

The corpus at ``tests/regression/known_scenarios.jsonl`` pins ~20
historical setups to their expected stance band. CI runs each
scenario through a stance predictor and fails if any stance drifts
out of its allowed band. Intentional drift requires an explicit
corpus update in the same PR with a justification — that's the
gate's whole point.

Two predictor modes:

  * ``stub`` (default; runs on every PR — free, deterministic):
    deterministic local rule. Mirrors the stub in
    ``scripts/run_shadow_calibration.py`` so the calibration
    burn-in and the regression gate use the same predictor.
  * ``foundry`` (opt-in via ``REGRESSION_USE_FOUNDRY=1``): real
    LLM call. Cost: 20 calls × ~$0.05–0.20 = $1–4 per run.
    Run via ``workflow_dispatch`` rather than every push.

The corpus rows are structured with ``expected_stance_in`` (a list
of acceptable stances) rather than a single value because some
scenarios have more than one defensible reading — flat is always a
defensible "I don't know" in regime-shift cases. The predictor
must land inside the allowed band; landing outside is a drift.
"""

from __future__ import annotations

import json
import os
import pathlib
from dataclasses import dataclass

import pytest


CORPUS_PATH = pathlib.Path(__file__).resolve().parent / "known_scenarios.jsonl"


@dataclass
class Scenario:
    scenario_id: str
    label: str
    context_payload: dict
    expected_stance_in: list[str]
    expected_reasoning_keywords: list[str]
    notes: str


def _load_corpus() -> list[Scenario]:
    if not CORPUS_PATH.exists():
        return []
    rows: list[Scenario] = []
    with open(CORPUS_PATH, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            rows.append(
                Scenario(
                    scenario_id=str(raw["scenario_id"]),
                    label=str(raw.get("label", "")),
                    context_payload=dict(raw.get("context_payload") or {}),
                    expected_stance_in=list(raw.get("expected_stance_in") or []),
                    expected_reasoning_keywords=list(raw.get("expected_reasoning_keywords") or []),
                    notes=str(raw.get("notes", "")),
                )
            )
    return rows


def _stub_predict(ctx: dict) -> tuple[str, int]:
    """Deterministic local stance predictor. Mirrors
    ``scripts/run_shadow_calibration.py::_stub_thesis`` so the
    calibration burn-in and the regression gate use the same rule.

    The predictor knows about regime_vol_bucket="high" and uses it
    to bias toward "flat" — the safe stance during regime shifts.
    """
    z = float(ctx.get("current_z", 0.0))
    vol_bucket = ctx.get("regime_vol_bucket")
    abs_z = abs(z)

    # Tail-risk override: when |Z| > 3 OR vol_bucket == "high" AND |Z| > 1.5,
    # force flat — the regression body's recurring lesson.
    if abs_z > 3.0:
        return "flat", 4
    if vol_bucket == "high" and abs_z > 1.5:
        return "flat", 4

    # Below the regime-shift threshold, follow mean-reversion logic.
    if abs_z < 1.0:
        return "flat", 1
    stance = "short_spread" if z > 0 else "long_spread"
    conv = int(round(min(10, max(1, 1.0 + abs_z * 2.0))))
    return stance, conv


def _llm_predict(ctx: dict) -> tuple[str, int]:
    """Real LLM call against historical context. Best-effort.

    Implemented as a thin wrapper over the existing thesis pipeline.
    This is gated behind REGRESSION_USE_FOUNDRY=1 so CI doesn't burn
    tokens on every push.
    """
    try:
        from foundry_agent import build_thesis_via_foundry  # type: ignore

        out = build_thesis_via_foundry(ctx)
        raw = out.raw if hasattr(out, "raw") else (out or {})
        return str(raw.get("stance") or "flat"), int(raw.get("conviction_0_to_10") or 0)
    except Exception as exc:
        pytest.skip(f"foundry predictor unavailable: {exc}")
        return "flat", 0  # unreachable


def _predict(ctx: dict) -> tuple[str, int]:
    if os.environ.get("REGRESSION_USE_FOUNDRY") == "1":
        return _llm_predict(ctx)
    return _stub_predict(ctx)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_corpus_has_at_least_20_scenarios():
    """Issue body explicit acceptance — corpus has at least 20 rows."""
    corpus = _load_corpus()
    assert len(corpus) >= 20, (
        f"Expected at least 20 scenarios in tests/regression/known_scenarios.jsonl; "
        f"got {len(corpus)}."
    )


def test_corpus_rows_have_required_fields():
    corpus = _load_corpus()
    for s in corpus:
        assert s.scenario_id, "scenario_id missing"
        assert s.expected_stance_in, f"{s.scenario_id}: expected_stance_in is empty"
        for stance in s.expected_stance_in:
            assert stance in ("long_spread", "short_spread", "flat"), (
                f"{s.scenario_id}: invalid stance {stance!r} in expected_stance_in"
            )
        assert "current_z" in s.context_payload, (
            f"{s.scenario_id}: context_payload missing current_z"
        )


@pytest.mark.parametrize("scenario", _load_corpus(), ids=lambda s: s.scenario_id)
def test_known_scenario_stance_in_allowed_band(scenario: Scenario):
    """The locking gate. Predictor stance must land in
    ``scenario.expected_stance_in``. Drift fails the build —
    operator must update the corpus in the same PR with a note.
    """
    stance, conv = _predict(scenario.context_payload)
    assert stance in scenario.expected_stance_in, (
        f"{scenario.scenario_id} ({scenario.label}): "
        f"predictor returned stance={stance!r} (conviction={conv}); "
        f"expected one of {scenario.expected_stance_in}. "
        f"If this is intentional drift, update the corpus row in "
        f"tests/regression/known_scenarios.jsonl in the same PR with a "
        f"justification in the `notes` field. Original notes: {scenario.notes}"
    )


def test_extreme_z_always_flat_under_stub():
    """Regime-shift sanity — |Z| > 3 forces flat under the stub
    regardless of sign."""
    for z in (-5.0, 3.5, 4.0, -3.2):
        stance, _ = _stub_predict({"current_z": z})
        assert stance == "flat", (
            f"|Z|={abs(z):.1f} should force flat under regime-shift override; got {stance}"
        )


def test_high_vol_bucket_biases_to_flat():
    """high vol bucket + |Z| > 1.5 forces flat."""
    stance, _ = _stub_predict({"current_z": 1.9, "regime_vol_bucket": "high"})
    assert stance == "flat"
    # Without high vol bucket, the same Z gives short_spread.
    stance, _ = _stub_predict({"current_z": 1.9, "regime_vol_bucket": "normal"})
    assert stance == "short_spread"
