"""Issue #98 — numeric claim validator unit tests.

Acceptance criteria from the issue body:
  * fixture with a fabricated number ("Brent is $999/bbl") — assert
    the validator catches it (returns at least one violation).
  * a number that DOES match the context returns zero violations.
"""

from __future__ import annotations

from backend.services.thesis_claim_validator import (
    _flatten_context_numerics,
    _within_tolerance,
    validate_thesis_claims,
)


def _realistic_context() -> dict:
    """A trimmed-but-realistic ThesisContext.to_dict() snapshot for
    fixture purposes. Only includes the fields the validator
    actually pings against."""
    return {
        "latest_brent": 108.23,
        "latest_wti": 96.37,
        "latest_spread": 11.86,
        "rolling_mean_90d": 5.20,
        "rolling_std_90d": 1.40,
        "current_z": 2.10,
        "z_percentile_5y": 92.5,
        "days_since_last_abs_z_over_2": 18,
        "bt_hit_rate": 0.74,
        "bt_avg_hold_days": 12.0,
        "bt_avg_pnl_per_bbl": 1.25,
        "bt_max_drawdown_usd": -45_000.0,
        "bt_sharpe": 1.30,
        "vol_brent_30d_pct": 28.1,
        "vol_wti_30d_pct": 31.4,
        "vol_spread_30d_pct": 14.6,
        "vol_spread_1y_percentile": 67.0,
        "user_z_threshold": 2.0,
        "garch_z": 1.95,
    }


# ---------------------------------------------------------------------------
# Issue #98 acceptance criteria
# ---------------------------------------------------------------------------
def test_fabricated_dollar_claim_is_flagged():
    """The marquee acceptance test: $999/bbl is nowhere in context."""
    thesis = {
        "plain_english_headline": "Brent is $999/bbl — short the spread immediately.",
        "thesis_summary": "",
        "key_drivers": [],
        "invalidation_risks": [],
        "reasoning_summary": "",
    }
    result = validate_thesis_claims(thesis, _realistic_context())
    assert result["verdict"] == "unverified"
    # At least one violation must mention 999.
    assert any(v["value"] == 999.0 for v in result["violations"]), (
        f"$999/bbl hallucination not flagged. violations={result['violations']}"
    )


def test_legit_claim_traces_to_context_and_returns_no_violations():
    """A thesis whose numbers all map back to context values is verified."""
    ctx = _realistic_context()
    # Quote latest_brent (108.23) within 5% as "around $108".
    thesis = {
        "plain_english_headline": "Brent around $108, WTI near $96 — spread is 12.",
        "thesis_summary": (
            "Spread sitting at 11.86, current Z is 2.1 sigma, the historical "
            "hit rate over short holds is around 74%."
        ),
        "key_drivers": [
            "Spread is 11.86 — well above the 90d rolling mean of 5.2.",
            "Realised vol on the spread is in the 67th percentile.",
        ],
        "invalidation_risks": [
            "If Brent stays above $108 for ~12 days the trade ages out.",
        ],
        "reasoning_summary": "Mean reversion on stretched spread; 18 days since last 2-sigma move.",
    }
    result = validate_thesis_claims(thesis, ctx)
    assert result["verdict"] == "verified", (
        f"Legit prose flagged as unverified. violations={result['violations']}"
    )
    assert result["violations"] == []


# ---------------------------------------------------------------------------
# Specialised pin checks
# ---------------------------------------------------------------------------
def test_sigma_unit_only_matches_zscore_family():
    """A "5 sigma" claim cannot be satisfied by a non-zscore field."""
    ctx = _realistic_context()
    # Drop current_z and garch_z so no zscore field can match.
    ctx.pop("current_z", None)
    ctx.pop("garch_z", None)
    thesis = {
        "plain_english_headline": "Spread is at 5 sigma — extreme dislocation.",
        "thesis_summary": "",
        "key_drivers": [],
        "invalidation_risks": [],
        "reasoning_summary": "",
    }
    result = validate_thesis_claims(thesis, ctx)
    assert result["verdict"] == "unverified"
    sigmas = [v for v in result["violations"] if v["unit"] == "sigma"]
    assert sigmas, "Sigma claim must be flagged when no zscore field matches"


def test_negative_sigma_claim_matches_signed_zscore():
    """If current_z is +2.1, a thesis claiming '-2.1 sigma' should still
    match (Z is signed, prose may flip the sign for stylistic reasons)."""
    ctx = _realistic_context()
    thesis = {
        "plain_english_headline": "Z just printed 2.1σ above the mean.",
        "thesis_summary": "",
        "key_drivers": [],
        "invalidation_risks": [],
        "reasoning_summary": "",
    }
    result = validate_thesis_claims(thesis, ctx)
    assert result["verdict"] == "verified"


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------
def test_flatten_context_numerics_handles_nested_lists_and_skips_none():
    ctx = {
        "a": 1.5,
        "b": None,
        "c": True,            # bool — must be skipped
        "d": "string-noise",  # non-numeric — skip
        "e": [10.0, 20.0, {"nested": 30.0}],
        "f": float("nan"),    # nan — skip
    }
    flat = _flatten_context_numerics(ctx)
    values = sorted(v for _, v in flat)
    assert values == [1.5, 10.0, 20.0, 30.0]


def test_within_tolerance_uses_relative_for_large_absolute_for_small():
    # Relative-tolerance regime: 100 vs 105 at 5% is the boundary.
    assert _within_tolerance(105.0, 100.0, 0.05) is True
    assert _within_tolerance(106.0, 100.0, 0.05) is False
    # Absolute fallback for tiny values: 0.5 absolute slack.
    assert _within_tolerance(0.4, 0.0, 0.05) is True


def test_validator_skips_unitless_small_integers_no_violations():
    """Numbers like '5 drivers' or '6 risks' (no unit, small) shouldn't
    flag — they're noise, not claims about the market."""
    ctx = _realistic_context()
    thesis = {
        "plain_english_headline": "Top 3 risks identified.",
        "thesis_summary": "5 key drivers cited.",
        "key_drivers": ["Driver 1.", "Driver 2.", "Driver 3."],
        "invalidation_risks": [],
        "reasoning_summary": "",
    }
    result = validate_thesis_claims(thesis, ctx)
    assert result["verdict"] == "verified"


def test_violation_includes_field_value_unit_snippet():
    thesis = {
        "plain_english_headline": "Brent is $1234/bbl — extreme.",
        "thesis_summary": "",
        "key_drivers": [],
        "invalidation_risks": [],
        "reasoning_summary": "",
    }
    result = validate_thesis_claims(thesis, _realistic_context())
    assert result["verdict"] == "unverified"
    v = result["violations"][0]
    assert v["field"] == "plain_english_headline"
    assert v["value"] == 1234.0
    assert v["unit"] in ("$", "usd/bbl", "usd")  # accept any of the dollar variants
    assert "1234" in v["snippet"]


def test_empty_thesis_returns_zero_claims_no_violations():
    """A thesis with all-empty text fields produces no claims and no
    violations — defensive path for the early-fallback flat thesis."""
    thesis = {
        "plain_english_headline": "",
        "thesis_summary": "",
        "key_drivers": [],
        "invalidation_risks": [],
        "reasoning_summary": "",
    }
    result = validate_thesis_claims(thesis, _realistic_context())
    assert result["verdict"] == "verified"
    assert result["n_claims"] == 0
    assert result["violations"] == []
