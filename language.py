"""UI language pass — authoritative rename table + qualitative bands.

This module is the single source of truth for every UI-facing finance string
in the app. Render sites pull display names from ``TERMS`` and qualitative
descriptions from ``describe_stretch`` / ``describe_confidence`` /
``describe_correlation`` / ``describe_stance``.

Design intent
-------------
Audience is "a smart generalist with no finance background — a trader's
buddy explaining over beers." Every technical term (Z-score, dislocation,
Sharpe ratio, Jones Act, etc.) lives in the ``TOOLTIPS`` map so
finance-literate readers can still map back to the math.

Pure module. No Streamlit import. No runtime I/O. Safe to import in tests.

See ``docs/designs/ui-polish.md`` → "Corrections (2026-04-22 01:05Z):
branding + deep language pass" for the full rename table and band cut-offs.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Rename table — authoritative mapping from internal key to UI display string.
# ---------------------------------------------------------------------------
TERMS: dict[str, str] = {
    # Top-level concepts ----------------------------------------------------
    "trade_idea": "Trade idea",
    "stretch": "Spread Stretch",
    "stretch_alert": "Alert when stretched this much",
    "stretch_series": "How the stretch has moved over the last 90 days",
    "stretch_extreme": "Very extreme stretch",
    "std_unit": "times the usual daily move",
    "mean_reversion": "Snap-back to normal",
    "backtest_label": "How this strategy would have worked in the past",

    # Risk / return metrics -------------------------------------------------
    "sharpe": "Risk-adjusted return",
    "drawdown": "Worst drop during a losing run",
    "vol": "How jumpy prices are",

    # Inventory / depletion -------------------------------------------------
    "depletion": "How fast stocks are running down (barrels/day)",
    "floor_breach": "When stocks run out",
    "floor": "Low point / red line",

    # Fleet / flags ---------------------------------------------------------
    "flag_state": "Country the ship is registered in",
    "jones_act": "US-flagged or US-bound",
    "shadow_risk": "Flags of convenience (Panama, Liberia, ...)",
    "sanctioned": "Sanctioned-country flags (Russia, Iran, Venezuela)",

    # Materiality + watchlist -----------------------------------------------
    "materiality": "Whether anything changed meaningfully",
    "catalysts": "What could move the market next",
    "invalidations": "What would break this trade idea",

    # Confidence + stance ---------------------------------------------------
    #
    # Row 13 (Phase C): stance copy is hypothetical, not imperative. "Buy /
    # Sell / Wait" read as instructions; "Lean long / Lean short / Stand
    # aside" read as calibrated dispositions, which is the only honest
    # framing for a structured output that also ships an
    # ``invalidation_risks`` list and a ``data_caveats`` strip. See
    # docs/reviews/_synthesis.md → Row 13.
    "confidence": "Confidence",
    "long_spread": "Lean long",
    "short_spread": "Lean short",
    "flat": "Stand aside",
}


# ---------------------------------------------------------------------------
# Tooltip table — every ``TERMS`` key has one. Tooltip template:
#   "Also called **<technical term>**. <plain-English definition>.
#    <how to read the current value>."
# ---------------------------------------------------------------------------
TOOLTIPS: dict[str, str] = {
    "trade_idea": (
        "Also called the **trade thesis**. A structured view on what the "
        "market is doing and what that implies you could do about it — "
        "stance, confidence, entry/exit, sizing, risks."
    ),
    "stretch": (
        "Also called **Z-score** or **dislocation**. How far today's "
        "Brent-WTI spread is from its normal 90-day range, expressed as "
        "multiples of the usual daily move. 2.4 means the spread is 2.4x "
        "its usual wobble above average — statistically unusual."
    ),
    "stretch_alert": (
        "Also called the **Z-score alert threshold**. The minimum stretch "
        "level before the app flags the spread as interesting. Lower = more "
        "signals but noisier; higher = fewer but sharper."
    ),
    "stretch_series": (
        "Also called the **90-day rolling Z-score series**. The path the "
        "stretch has walked over the last 90 trading days — useful for "
        "seeing whether the current reading is an isolated spike or a trend."
    ),
    "stretch_extreme": (
        "Also called an **extreme dislocation** (|Z| >= 3.2). Statistically "
        "rare — the spread is this far from its normal range only a few "
        "times per year on average."
    ),
    "std_unit": (
        "Also called a **standard deviation** (sigma). One unit equals the "
        "typical daily swing in the spread, estimated from the last 90 "
        "days. Two units = roughly twice the usual wobble."
    ),
    "mean_reversion": (
        "Also called **mean reversion**. The tendency for a stretched "
        "spread to drift back toward its average over time. The math "
        "assumes Brent and WTI share a long-run relationship (cointegration)."
    ),
    "backtest_label": (
        "Also called the **historical backtest**. Replays the strategy on "
        "past data with today's rules to estimate how often it would have "
        "won, what it would have made per trade, and its worst losing run."
    ),
    "sharpe": (
        "Also called the **Sharpe ratio**. Average return per unit of risk, "
        "annualised. Rule of thumb: > 1 is decent, > 2 is excellent, "
        "< 0.5 is noise."
    ),
    "drawdown": (
        "Also called the **maximum drawdown**. The deepest peak-to-trough "
        "drop in the strategy's cumulative PnL over the historical window. "
        "What you'd have bled at the worst point if you'd started then."
    ),
    "vol": (
        "Also called **realised volatility**. How much prices swing day to "
        "day, annualised. High = big daily moves; low = calm tape. "
        "Compared against the last year's range for context."
    ),
    "depletion": (
        "Also called the **depletion rate**. How many barrels of crude "
        "inventory are disappearing per day on average, estimated from a "
        "linear fit to the recent trailing window."
    ),
    "floor_breach": (
        "Also called an **inventory floor breach**. The projected date "
        "inventory would hit the user-set floor if the current drawdown "
        "pace held constant."
    ),
    "floor": (
        "Also called the **inventory floor**. The barrel level you want "
        "stocks to stay above. A red line on the inventory chart."
    ),
    "flag_state": (
        "Also called the **vessel flag state**. The country a ship is "
        "legally registered in — drives which rules it operates under."
    ),
    "jones_act": (
        "Also called the **Jones Act / Domestic** bucket. Vessels flagged "
        "in the US or carrying cargo bound for a US port — the subset of "
        "fleet insulated from foreign-flag competition."
    ),
    "shadow_risk": (
        "Also called the **shadow-fleet / flags-of-convenience** bucket. "
        "Vessels registered in Panama, Liberia, Marshall Islands, Malta — "
        "common hosts for sanctions-sensitive cargoes."
    ),
    "sanctioned": (
        "Also called the **sanctioned-country flag** bucket. Vessels "
        "registered in Russia, Iran, or Venezuela — cargo from these "
        "origins is subject to US/EU sanctions."
    ),
    "materiality": (
        "Also called **materiality**. Whether the underlying data has "
        "changed enough since the last thesis to warrant regenerating — "
        "avoids burning model tokens on millisecond noise."
    ),
    "catalysts": (
        "Also called the **catalyst watchlist**. Dated events (EIA release, "
        "OPEC meeting, inventory data) the model expects could meaningfully "
        "move the spread."
    ),
    "invalidations": (
        "Also called the **invalidation risks** or **what-would-make-us-wrong**. "
        "The specific conditions under which this trade idea stops being valid "
        "and you should exit."
    ),
    "confidence": (
        "Also called **conviction** (0-10). How strong the model judges "
        "the signal to be, on a 10-point scale. Calibrated down when the "
        "historical backtest is weak or the pair fails cointegration."
    ),
    "long_spread": (
        "Also called a **long spread** stance. Buy Brent and sell WTI in "
        "equal-risk proportions — profit when the Brent-WTI gap widens."
    ),
    "short_spread": (
        "Also called a **short spread** stance. Sell Brent and buy WTI in "
        "equal-risk proportions — profit when the Brent-WTI gap narrows."
    ),
    "flat": (
        "Also called **flat** or **stand aside**. The model doesn't see a "
        "tradeable edge right now — sit on hands, wait for the next signal."
    ),
}


# ---------------------------------------------------------------------------
# Qualitative bands (frozen — see design spec for cut-offs).
# ---------------------------------------------------------------------------
def describe_stretch(abs_z: float) -> str:
    """Qualitative label for the spread-stretch |Z| value.

    Accepts negative values — we take ``abs()`` so callers don't have to.

    Bands:
        < 0.7   → "Calm"
        < 1.3   → "Normal"
        < 2.3   → "Stretched"
        < 3.2   → "Very Stretched"
        >= 3.2  → "Extreme"
    """
    a = abs(float(abs_z))
    if a < 0.7:
        return "Calm"
    if a < 1.3:
        return "Normal"
    if a < 2.3:
        return "Stretched"
    if a < 3.2:
        return "Very Stretched"
    return "Extreme"


def describe_confidence(n: int) -> str:
    """Qualitative label for a 1-10 conviction value.

    Bands:
        1-3   → "Low"
        4-6   → "Medium"
        7-8   → "High"
        9-10  → "Very High"
    """
    v = int(n)
    if v <= 3:
        return "Low"
    if v <= 6:
        return "Medium"
    if v <= 8:
        return "High"
    return "Very High"


def describe_correlation(r: float) -> str:
    """Qualitative label for a correlation coefficient (absolute value).

    Bands on ``abs(r)``:
        < 0.3   → "Weak"
        < 0.6   → "Moderate"
        >= 0.6  → "Strong"
    """
    a = abs(float(r))
    if a < 0.3:
        return "Weak"
    if a < 0.6:
        return "Moderate"
    return "Strong"


def describe_stance(stance: str) -> str:
    """Map a schema stance enum to its display verb.

    Unknown / unmapped values pass through unchanged so upstream code that
    logs raw stance strings stays honest.
    """
    mapping = {
        # Row 13 (Phase C): hypothetical, not imperative — see the TERMS
        # table for full rationale.
        "LONG_SPREAD": "Lean long",
        "SHORT_SPREAD": "Lean short",
        "FLAT": "Stand aside",
        "STAND_ASIDE": "Stand aside",
        # Lower-case variants used inside the JSON schema:
        "long_spread": "Lean long",
        "short_spread": "Lean short",
        "flat": "Stand aside",
        "stand_aside": "Stand aside",
    }
    return mapping.get(stance, stance)


def with_tooltip(key: str) -> tuple[str, str]:
    """Return ``(display_name, help_text)`` for a ``TERMS`` key.

    Raises ``KeyError`` on unknown keys — that's the contract. Callers pass
    known keys; typos fail loudly.
    """
    return TERMS[key], TOOLTIPS[key]


__all__ = [
    "TERMS",
    "TOOLTIPS",
    "describe_stretch",
    "describe_confidence",
    "describe_correlation",
    "describe_stance",
    "with_tooltip",
]
