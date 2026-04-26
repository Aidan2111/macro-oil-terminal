"""Regime service — term-structure + realized-vol bucket classifier.

Two badges on the hero card driven by this service:

  1. **Term structure** — ``contango`` when the front month is below
     the deferred month, ``backwardation`` when above. We use the
     Brent-WTI spread sign as a proxy when an explicit forward curve
     isn't on hand: a *positive* Brent-WTI spread (Brent over WTI)
     historically lines up with WTI-side contango (cheap front WTI
     vs. seaborne Brent), so we surface "contango" when the spread is
     positive and "backwardation" when it inverts. The frontend
     tooltip explains the proxy in plain English.

  2. **Vol bucket** — bucket the latest 20-day realized volatility of
     the spread into ``low`` / ``normal`` / ``high`` based on its
     percentile within the trailing 1-year history. <33 → low, 33-66
     → normal, >66 → high. Percentile is the 1-year quantile of the
     20-day rolling realized vol, mirroring how Bloomberg's spread
     terminal slices the same series.

The contract returned here is the source-of-truth shape for the React
``RegimeBadges`` component and the ``ThesisContext.regime`` field.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

from . import _compat  # noqa: F401 — sets sys.path for legacy imports


@dataclass(frozen=True)
class RegimeStats:
    term_structure: str            # "contango" | "backwardation" | "flat"
    vol_bucket: str                # "low" | "normal" | "high" | "unknown"
    vol_percentile: float          # 0..100; NaN when history is too thin
    realized_vol_20d_pct: float    # latest annualised realized vol (%)
    spread_sign: float             # +1 / 0 / -1 — surface for the LLM
    message: str                   # "" on the happy path; reason on fallback

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        for k in ("vol_percentile", "realized_vol_20d_pct"):
            v = d[k]
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                d[k] = None
        return d


def _classify_term_structure(brent: float, wti: float) -> tuple[str, float]:
    """Map the latest Brent–WTI spread to a regime label.

    Brent > WTI ⇒ "contango" (proxy: front-month US barrels priced
    below seaborne Brent). Reversal ⇒ "backwardation". Tiny spreads
    (|Δ| < 0.25 USD) collapse to "flat" so noise doesn't flicker the
    badge.
    """
    spread = float(brent) - float(wti)
    if not math.isfinite(spread):
        return "flat", 0.0
    if spread > 0.25:
        return "contango", 1.0
    if spread < -0.25:
        return "backwardation", -1.0
    return "flat", 0.0


def _bucket_vol(percentile: float) -> str:
    if not math.isfinite(percentile):
        return "unknown"
    if percentile < 33.3:
        return "low"
    if percentile < 66.7:
        return "normal"
    return "high"


def detect_regime(df: Any) -> RegimeStats:
    """Classify the current regime from a spread DataFrame.

    ``df`` carries the same columns as
    ``quantitative_models.compute_spread_zscore`` (Brent, WTI, Spread).
    Empty / shape-broken inputs collapse to a neutral fallback so the
    hero card never blanks.
    """
    try:
        import numpy as np  # type: ignore
        import pandas as pd  # type: ignore
    except Exception as exc:  # pragma: no cover
        return RegimeStats(
            term_structure="flat",
            vol_bucket="unknown",
            vol_percentile=float("nan"),
            realized_vol_20d_pct=float("nan"),
            spread_sign=0.0,
            message=f"pandas/numpy unavailable: {exc!r}",
        )

    if (
        df is None
        or not isinstance(df, pd.DataFrame)
        or df.empty
        or "Brent" not in df.columns
        or "WTI" not in df.columns
    ):
        return RegimeStats(
            term_structure="flat",
            vol_bucket="unknown",
            vol_percentile=float("nan"),
            realized_vol_20d_pct=float("nan"),
            spread_sign=0.0,
            message="missing Brent/WTI columns",
        )

    try:
        latest_brent = float(df["Brent"].dropna().iloc[-1])
        latest_wti = float(df["WTI"].dropna().iloc[-1])
    except Exception:
        return RegimeStats(
            term_structure="flat",
            vol_bucket="unknown",
            vol_percentile=float("nan"),
            realized_vol_20d_pct=float("nan"),
            spread_sign=0.0,
            message="no usable Brent/WTI tail",
        )

    term, sign = _classify_term_structure(latest_brent, latest_wti)

    spread_series = (df["Brent"] - df["WTI"]).dropna()
    if len(spread_series) < 25:
        return RegimeStats(
            term_structure=term,
            vol_bucket="unknown",
            vol_percentile=float("nan"),
            realized_vol_20d_pct=float("nan"),
            spread_sign=sign,
            message=f"vol history too short (n={len(spread_series)})",
        )

    # Daily *changes* in the spread → 20-day stdev → annualise by sqrt(252).
    delta = spread_series.diff().dropna()
    rolling_vol = delta.rolling(20).std(ddof=0) * float(np.sqrt(252.0)) * 100.0
    rolling_vol = rolling_vol.replace([np.inf, -np.inf], np.nan).dropna()
    if rolling_vol.empty:
        return RegimeStats(
            term_structure=term,
            vol_bucket="unknown",
            vol_percentile=float("nan"),
            realized_vol_20d_pct=float("nan"),
            spread_sign=sign,
            message="rolling vol all-NaN",
        )

    latest_vol = float(rolling_vol.iloc[-1])
    history = rolling_vol.tail(252)  # ~1 trading year
    if history.empty:
        percentile = float("nan")
    else:
        percentile = float((history <= latest_vol).mean() * 100.0)
    bucket = _bucket_vol(percentile)

    return RegimeStats(
        term_structure=term,
        vol_bucket=bucket,
        vol_percentile=percentile,
        realized_vol_20d_pct=latest_vol,
        spread_sign=sign,
        message="",
    )


__all__ = [
    "RegimeStats",
    "detect_regime",
]
