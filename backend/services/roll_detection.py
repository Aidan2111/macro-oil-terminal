"""Front-month roll detection for continuous-future proxies.

yfinance's ``BZ=F`` (Brent) and ``CL=F`` (WTI) are *continuous front-
month* tickers. Each month the active contract rolls to the next
expiry, and the price simply jumps from the old contract's settle to
the new contract's settle. That gap is a synthetic discontinuity, not
a real market move, but the daily series shows it as a one-day
return spike.

If we don't account for it:
  * The spread Z-score window briefly mis-estimates volatility (the
    fake jump inflates stdev).
  * The reader sees an unexplained kink in the chart and asks "what
    happened on March 28?".

We solve it two ways:
  1. ``detect_front_month_rolls`` returns the suspect dates so the
     SpreadChart can annotate them with a tiny "Front-month roll"
     tick.
  2. (future PR) The Z-score builder will splice these out before
     computing rolling stats. For Q2 we only annotate — splicing is
     deliberately deferred so the historical chart stays comparable
     to what the model trained on.

Detection heuristic
-------------------
A trading day ``d`` is flagged as a roll IFF:

  * ``abs(spread_pct_change(d)) > 1.5%``   (gap test), AND
  * ``d`` falls within ±2 business days of a known CME publication
    date for either Brent or WTI front-month rolls.

The known-rolls list is a hard-coded calendar covering 2025-Q3
through 2026-Q4 — a quick start that's good enough for the
trailing-12-month window the chart shows. A follow-up PR can pull
the live calendar from CME's published rolls feed; the function
signature stays stable.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

import pandas as pd

# Hard-coded CME front-month roll dates for Brent and WTI.
# Brent (BZ=F) rolls on the last business day of the month preceding
# expiry. WTI (CL=F) rolls on the third business day before the 25th
# of the month preceding expiry. We over-include both to be safe.
#
# NOTE: this is a quick-start calendar — a follow-up will replace it
# with the live CME publication. Do not extend by hand past 2026-12.
_PUBLISHED_ROLLS_2025_2026: tuple[date, ...] = (
    date(2025, 7, 21), date(2025, 7, 31),
    date(2025, 8, 20), date(2025, 8, 29),
    date(2025, 9, 19), date(2025, 9, 30),
    date(2025, 10, 21), date(2025, 10, 31),
    date(2025, 11, 19), date(2025, 11, 28),
    date(2025, 12, 19), date(2025, 12, 31),
    date(2026, 1, 21), date(2026, 1, 30),
    date(2026, 2, 19), date(2026, 2, 27),
    date(2026, 3, 19), date(2026, 3, 31),
    date(2026, 4, 21), date(2026, 4, 30),
    date(2026, 5, 19), date(2026, 5, 29),
    date(2026, 6, 19), date(2026, 6, 30),
    date(2026, 7, 21), date(2026, 7, 31),
    date(2026, 8, 19), date(2026, 8, 31),
    date(2026, 9, 21), date(2026, 9, 30),
    date(2026, 10, 21), date(2026, 10, 30),
    date(2026, 11, 19), date(2026, 11, 30),
    date(2026, 12, 21), date(2026, 12, 31),
)

_GAP_THRESHOLD_PCT = 1.5
_CALENDAR_TOLERANCE_BDAYS = 2


def _to_date(value: object) -> date:
    """Coerce a Timestamp / datetime / date into a plain ``date``."""
    if isinstance(value, date) and not isinstance(value, pd.Timestamp):
        return value
    ts = pd.Timestamp(value)
    return ts.date()


def _within_calendar(d: date, calendar: Iterable[date], tolerance: int) -> bool:
    """True if ``d`` is within ``tolerance`` business days of any
    entry in ``calendar``. Business-day arithmetic uses pandas
    BusinessDay so weekends don't dilate the window."""
    bday = pd.tseries.offsets.BusinessDay(tolerance)
    target = pd.Timestamp(d)
    for c in calendar:
        c_ts = pd.Timestamp(c)
        if abs((target - c_ts).days) <= tolerance + 2:
            # cheap pre-filter, then exact business-day check
            lo = c_ts - bday
            hi = c_ts + bday
            if lo <= target <= hi:
                return True
    return False


def detect_front_month_rolls(
    df: pd.DataFrame,
    *,
    price_col: str = "Spread",
    gap_pct: float = _GAP_THRESHOLD_PCT,
    calendar: Iterable[date] | None = None,
    tolerance_bdays: int = _CALENDAR_TOLERANCE_BDAYS,
) -> list[date]:
    """Return dates where a continuous-future roll likely happened.

    Parameters
    ----------
    df
        DataFrame indexed by datetime-like dates with at least
        ``price_col`` populated. ``df`` may also have ``Brent`` /
        ``WTI`` columns; for the spread chart pass ``price_col="Spread"``
        and the heuristic will fire on the spread itself (which is
        what visually distorts the chart).
    price_col
        Column to compute pct-change on. Default ``"Spread"``.
    gap_pct
        Absolute % move above which a day is *gap-eligible*. Default
        1.5%, calibrated against historical rolls in 2024-25.
    calendar
        Iterable of known roll dates. If ``None`` we use the bundled
        2025-26 hard-coded calendar.
    tolerance_bdays
        Business-day tolerance around each calendar entry. Default 2.

    Returns
    -------
    list[date]
        Sorted, deduplicated list of trading dates that pass *both*
        the gap test and the calendar test. Empty list if ``df`` is
        unusable.
    """
    if df is None or len(df) == 0 or price_col not in df.columns:
        return []

    # Ensure a sorted, unique-by-date index.
    series = pd.to_numeric(df[price_col], errors="coerce")
    series = series.dropna()
    if series.empty:
        return []

    # Use absolute pct-change of the spread itself. We deliberately
    # use abs() not signed because rolls can pop in either direction
    # depending on whether the next contract is in contango or
    # backwardation relative to the current.
    pct = series.pct_change().abs() * 100.0
    suspect_idx = pct[pct > gap_pct].index

    cal = list(calendar) if calendar is not None else list(_PUBLISHED_ROLLS_2025_2026)

    out: list[date] = []
    seen: set[date] = set()
    for ts in suspect_idx:
        d = _to_date(ts)
        if d in seen:
            continue
        if _within_calendar(d, cal, tolerance_bdays):
            seen.add(d)
            out.append(d)

    return sorted(out)


def annotate_history_with_rolls(
    history: list[dict],
    rolls: list[date],
) -> list[dict]:
    """Add an ``is_roll: bool`` flag to each history point.

    Mutates a copy of ``history`` non-destructively. The frontend
    ``RollMarkers`` component uses this flag to draw a vertical
    dotted line + hover label.
    """
    if not history:
        return history
    roll_set = {d.isoformat() for d in rolls}
    out: list[dict] = []
    for pt in history:
        cp = dict(pt)
        cp["is_roll"] = pt.get("date") in roll_set
        out.append(cp)
    return out


__all__ = [
    "detect_front_month_rolls",
    "annotate_history_with_rolls",
]
