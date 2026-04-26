"""Real options-chain validation for thesis IV / skew citations.

When a thesis says something like "BZ Jul calls are pricing 38% IV,
~5 vol points rich to realised", we want the live yfinance options
chain to support that number. If yfinance returns an empty chain
(rate-limited / ticker glitch / market closed) or the cited IV is
>10% off the chain median, we surface a "stale options data" badge
on the hero so the reader knows the citation can't be re-checked.

Hard requirement: this MUST NOT block thesis generation. yfinance
can be flaky; if the validation can't run, we degrade to a "stale"
warning rather than throwing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from . import _compat  # noqa: F401


# Match patterns like:
#   "38% IV"  "implied vol of 0.42"  "~22 vol"  "skew of 4 vols"
#   "IV around 38%"  "IV is 25%"  "IV ~ 30%"
# Two flavours: number-then-keyword ("38% IV") and keyword-then-number
# ("IV is 25%"). We try the number-first form preferentially because
# when both shapes occur in the same sentence the cited number is
# usually the leading numeric token (e.g. "~38% IV — five vol points
# rich to realised").
_IV_PATTERN_NUM_FIRST = re.compile(
    r"(?<![\w.])"
    r"(\d{1,3}(?:\.\d+)?)\s*%?\s*"
    r"(?:vol(?:atility)?\s*points?|vols?|IV|implied\s*vol(?:atility)?)"
    r"(?!\w)",
    re.IGNORECASE,
)
_IV_PATTERN_KW_FIRST = re.compile(
    r"(?:implied\s*vol(?:atility)?|IV|vol(?!ume))\s*"
    r"(?:of|=|:|~|approximately|around|about|near|is|at|sits\s*at)?\s*"
    r"~?\s*"
    r"(\d{1,3}(?:\.\d+)?)\s*%?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class OptionsValidation:
    """Outcome of a thesis options-citation check.

    Attributes
    ----------
    valid
        ``True`` if the chain is reachable AND the cited number sits
        within ``tolerance_pct`` of the chain median IV.
    message
        Short human-readable message — rendered into the badge on
        the hero card. Always populated.
    cited_iv
        The IV (in decimal, e.g. ``0.38`` for 38%) we extracted from
        the thesis text, or ``None`` if no citation was found.
    chain_median_iv
        Median IV across the front-expiry strikes near ATM, or
        ``None`` if the chain couldn't be fetched.
    stale
        ``True`` IFF the chain itself was unreachable. Distinct from
        ``not valid`` — the citation may simply be out of tolerance.
    """

    valid: bool
    message: str
    cited_iv: Optional[float] = None
    chain_median_iv: Optional[float] = None
    stale: bool = False

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "message": self.message,
            "cited_iv": self.cited_iv,
            "chain_median_iv": self.chain_median_iv,
            "stale": self.stale,
        }


def _extract_cited_iv(text: str) -> Optional[float]:
    """Pull the first numeric IV citation out of free-form thesis
    text. Returns a decimal (0.38) or ``None``.

    Tries number-first ("38% IV", "22 vols") before keyword-first
    ("IV around 38%") so that a sentence which contains both a
    citation and a comparison phrase ("five vol points rich to
    realised") locks onto the citation rather than the comparison.
    """
    if not text:
        return None
    for pat in (_IV_PATTERN_NUM_FIRST, _IV_PATTERN_KW_FIRST):
        m = pat.search(text)
        if not m:
            continue
        raw = float(m.group(1))
        # If the value is a percentage (>1.5), convert to decimal.
        return raw / 100.0 if raw > 1.5 else raw
    return None


def _fetch_chain_median_iv(ticker: str) -> Optional[float]:
    """Fetch the front-expiry options chain via yfinance and return
    the median ATM-ish implied volatility. Returns ``None`` on any
    upstream failure — caller treats that as "stale"."""
    try:
        import yfinance as yf  # type: ignore
    except Exception:
        return None

    try:
        t = yf.Ticker(ticker)
        expiries = getattr(t, "options", None) or ()
        if not expiries:
            return None
        chain = t.option_chain(expiries[0])
        # ATM-ish = within 5% of last close. Falls back to all rows
        # when last is unknown.
        try:
            last = float(t.history(period="5d")["Close"].iloc[-1])
        except Exception:
            last = None

        ivs: list[float] = []
        for frame_name in ("calls", "puts"):
            frame = getattr(chain, frame_name, None)
            if frame is None or frame.empty or "impliedVolatility" not in frame.columns:
                continue
            sub = frame
            if last is not None and "strike" in frame.columns:
                lo, hi = last * 0.95, last * 1.05
                sub = frame[(frame["strike"] >= lo) & (frame["strike"] <= hi)]
                if sub.empty:
                    sub = frame
            for v in sub["impliedVolatility"].dropna().tolist():
                if 0 < float(v) < 5:  # filter pathological IVs
                    ivs.append(float(v))
        if not ivs:
            return None
        ivs.sort()
        return ivs[len(ivs) // 2]
    except Exception:
        return None


def validate_options_citation(
    thesis_options_section: str,
    ticker: str,
    *,
    tolerance_pct: float = 10.0,
    chain_iv_override: Optional[float] = None,
) -> OptionsValidation:
    """Cross-check the thesis IV citation against the live options
    chain.

    Parameters
    ----------
    thesis_options_section
        Free-form text from the thesis, typically the "Options /
        Skew" paragraph. Empty / None is a no-op (returns ``valid``
        with an explanatory message).
    ticker
        yfinance ticker — typically ``"BZ=F"`` or ``"CL=F"``. Note:
        yfinance options coverage on continuous futures is
        intermittent; we tolerate ``None`` chain by emitting a
        ``stale`` validation rather than raising.
    tolerance_pct
        How far the cited IV may sit from the chain median before
        we flag it. Default ±10%.
    chain_iv_override
        Test seam — bypasses the live yfinance call.
    """
    if not thesis_options_section or not thesis_options_section.strip():
        return OptionsValidation(
            valid=True,
            message="No options citation in thesis",
            cited_iv=None,
            chain_median_iv=None,
            stale=False,
        )

    cited = _extract_cited_iv(thesis_options_section)

    chain_iv = chain_iv_override
    if chain_iv is None:
        chain_iv = _fetch_chain_median_iv(ticker)

    if chain_iv is None:
        return OptionsValidation(
            valid=False,
            message="Options chain unavailable — citation not verified",
            cited_iv=cited,
            chain_median_iv=None,
            stale=True,
        )

    # A zero (or negative) chain median IV is a stale-data signal —
    # yfinance occasionally returns an empty chain that aggregates to
    # zero. Surface that as stale regardless of whether a citation
    # was found, so the downstream badge renders correctly.
    if chain_iv <= 0:
        return OptionsValidation(
            valid=False,
            message="Options chain returned zero IV — likely stale",
            cited_iv=cited,
            chain_median_iv=chain_iv,
            stale=True,
        )

    if cited is None:
        # No numeric citation but the section exists — pass-through
        # since we have nothing to check against.
        return OptionsValidation(
            valid=True,
            message="Options chain checked",
            cited_iv=None,
            chain_median_iv=chain_iv,
            stale=False,
        )

    delta_pct = abs(cited - chain_iv) / chain_iv * 100.0
    if delta_pct <= tolerance_pct:
        return OptionsValidation(
            valid=True,
            message=f"Options chain confirms cited IV (delta {delta_pct:.1f}%)",
            cited_iv=cited,
            chain_median_iv=chain_iv,
            stale=False,
        )

    return OptionsValidation(
        valid=False,
        message=(
            f"Cited IV ({cited * 100:.1f}%) is {delta_pct:.1f}% off chain "
            f"median ({chain_iv * 100:.1f}%) — citation may be stale"
        ),
        cited_iv=cited,
        chain_median_iv=chain_iv,
        stale=False,
    )


__all__ = ["OptionsValidation", "validate_options_citation"]
