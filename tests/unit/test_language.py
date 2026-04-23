"""Unit tests for the `language` module (UIP-T0 language pass scaffolding).

These tests are the authoritative contract for the rename table + qualitative
bands. See ``docs/designs/ui-polish.md`` "Corrections" section for the full
table and band cut-offs.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# describe_stretch — qualitative bands on |Z|
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value,expected",
    [
        (0.5, "Calm"),
        (1.0, "Normal"),
        (2.0, "Stretched"),
        (3.0, "Very Stretched"),
        (4.0, "Extreme"),
        (-2.5, "Very Stretched"),  # abs(-2.5) = 2.5 → "Very Stretched"
        (-0.2, "Calm"),             # abs(-0.2) = 0.2 → "Calm"
    ],
)
def test_describe_stretch_bands(value, expected):
    from language import describe_stretch
    assert describe_stretch(value) == expected


# ---------------------------------------------------------------------------
# describe_confidence — 1-10 int → qualitative
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value,expected",
    [
        (1, "Low"),
        (3, "Low"),
        (4, "Medium"),
        (5, "Medium"),
        (6, "Medium"),
        (7, "High"),
        (8, "High"),
        (9, "Very High"),
        (10, "Very High"),
    ],
)
def test_describe_confidence_bands(value, expected):
    from language import describe_confidence
    assert describe_confidence(value) == expected


# ---------------------------------------------------------------------------
# describe_correlation — absolute value then bands
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value,expected",
    [
        (0.1, "Weak"),
        (0.29, "Weak"),
        (0.4, "Moderate"),
        (0.59, "Moderate"),
        (0.8, "Strong"),
        (0.95, "Strong"),
        (-0.7, "Strong"),   # negative → abs()
        (-0.1, "Weak"),     # negative → abs()
    ],
)
def test_describe_correlation_bands(value, expected):
    from language import describe_correlation
    assert describe_correlation(value) == expected


# ---------------------------------------------------------------------------
# Every TERMS key has a non-empty, substantive tooltip
# ---------------------------------------------------------------------------
def test_terms_has_tooltip_for_every_key():
    from language import TERMS, with_tooltip
    assert TERMS, "TERMS table must not be empty"
    for key in TERMS:
        display, help_text = with_tooltip(key)
        assert display, f"empty display string for key {key!r}"
        assert help_text, f"empty tooltip for key {key!r}"
        assert len(help_text) > 20, (
            f"tooltip for {key!r} too short ({len(help_text)} chars) — "
            f"tooltip contract requires a technical-term-preserving explainer"
        )


# ---------------------------------------------------------------------------
# Regression guard: none of the new display strings carry old jargon
# ---------------------------------------------------------------------------
def test_no_old_terms_in_terms_values():
    from language import TERMS
    banned = [
        "thesis",
        "dislocation",
        "z-score",
        "conviction",
        "standard deviation",
        "volatility",
        "sharpe",
        "jones act",
        "shadow risk",
        "cointegration",
        "half-life",
    ]
    for key, display in TERMS.items():
        lower = display.lower()
        for bad in banned:
            assert bad not in lower, (
                f"TERMS[{key!r}] = {display!r} still contains banned jargon {bad!r}"
            )
