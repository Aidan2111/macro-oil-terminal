"""Cointegration diagnostics for the Brent-WTI pair.

A mean-reversion strategy is only statistically valid when the two legs
are cointegrated. During structural breaks (2015 US export-ban lift,
2022 Russia/Urals, Q3 2025 WCS differential blowout) the pair
de-cointegrates and the dislocation signal is random noise.

Primary test: **Engle-Granger** — OLS on Brent ~ α + β·WTI, then
Augmented Dickey-Fuller on the residual. A low p-value (< 0.05)
rejects the unit-root null → the residual is stationary → the pair is
cointegrated.

Secondary metric: **half-life** of mean reversion, derived from the
AR(1) coefficient on the residual. A short half-life (< 30 days) means
the spread snaps back quickly; a long one (> 90 days) means the trade
has to be sized for a slow grind.

Every helper is defensive: on insufficient data or numerical failure,
returns a populated "inconclusive" dict rather than raising, so the UI
doesn't blank when the pair frame is short.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


try:
    from statsmodels.tsa.stattools import adfuller
    import statsmodels.api as sm
    _HAS_SM = True
except Exception:  # pragma: no cover
    adfuller = None  # type: ignore
    sm = None  # type: ignore
    _HAS_SM = False


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------
@dataclass
class CointegrationResult:
    p_value: float                 # ADF p-value on the OLS residual (lower = stronger)
    adf_stat: float                # The ADF test statistic itself
    hedge_ratio: float             # β from Brent = α + β·WTI + ε  (the "kg of WTI per kg of Brent")
    alpha: float                   # intercept α
    half_life_days: Optional[float]  # time for the spread to decay halfway back to mean; None if unit-root
    verdict: str                   # "cointegrated" | "weak" | "not_cointegrated" | "inconclusive"
    n_obs: int
    window: str                    # "full" or "rolling:<days>"
    is_cointegrated: bool          # convenience bool (p < 0.05)
    is_weak: bool                  # 0.05 ≤ p < 0.10

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Round for display — keep full precision in raw if the caller wants it
        for k in ("p_value", "adf_stat", "hedge_ratio", "alpha"):
            if d[k] is not None:
                d[k] = float(round(d[k], 4))
        if d["half_life_days"] is not None:
            d["half_life_days"] = float(round(d["half_life_days"], 1))
        return d


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------
def _half_life_from_residual(resid: pd.Series) -> Optional[float]:
    """Ornstein-Uhlenbeck half-life estimate from an AR(1) fit on the residual.

    If ε_t = ρ·ε_{t-1} + η_t with 0 < ρ < 1, the half-life is
    ln(2) / -ln(ρ) in units of the residual's sampling frequency.
    """
    if not _HAS_SM:
        return None
    r = resid.dropna()
    if len(r) < 20:
        return None
    lagged = r.shift(1).dropna()
    y = r.loc[lagged.index]
    X = sm.add_constant(lagged.values.astype(float))
    try:
        fit = sm.OLS(y.values.astype(float), X).fit()
    except Exception:
        return None
    rho = float(fit.params[1])
    if rho >= 1.0 or rho <= 0.0:
        return None
    try:
        return float(math.log(2.0) / -math.log(rho))
    except Exception:
        return None


def engle_granger(
    brent: pd.Series,
    wti: pd.Series,
    *,
    min_obs: int = 60,
) -> CointegrationResult:
    """Run Engle-Granger cointegration on the Brent/WTI pair over the full window.

    Returns an "inconclusive" result when statsmodels is unavailable or
    the series are too short.
    """
    brent = brent.dropna()
    wti = wti.dropna()
    idx = brent.index.intersection(wti.index)
    b = brent.loc[idx].astype(float)
    w = wti.loc[idx].astype(float)
    n = len(idx)

    if not _HAS_SM or n < min_obs:
        return CointegrationResult(
            p_value=float("nan"),
            adf_stat=float("nan"),
            hedge_ratio=float("nan"),
            alpha=float("nan"),
            half_life_days=None,
            verdict="inconclusive",
            n_obs=n,
            window="full",
            is_cointegrated=False,
            is_weak=False,
        )

    # OLS: Brent_t = alpha + beta * WTI_t + eps_t
    X = sm.add_constant(w.values)
    try:
        fit = sm.OLS(b.values, X).fit()
        alpha = float(fit.params[0])
        beta = float(fit.params[1])
        resid = b - (alpha + beta * w)
        adf = adfuller(resid.dropna().values, autolag="AIC")
        adf_stat = float(adf[0])
        p_value = float(adf[1])
    except Exception:
        return CointegrationResult(
            p_value=float("nan"),
            adf_stat=float("nan"),
            hedge_ratio=float("nan"),
            alpha=float("nan"),
            half_life_days=None,
            verdict="inconclusive",
            n_obs=n,
            window="full",
            is_cointegrated=False,
            is_weak=False,
        )

    half_life = _half_life_from_residual(resid)

    if p_value < 0.05:
        verdict = "cointegrated"
    elif p_value < 0.10:
        verdict = "weak"
    else:
        verdict = "not_cointegrated"

    return CointegrationResult(
        p_value=p_value,
        adf_stat=adf_stat,
        hedge_ratio=beta,
        alpha=alpha,
        half_life_days=half_life,
        verdict=verdict,
        n_obs=n,
        window="full",
        is_cointegrated=bool(p_value < 0.05),
        is_weak=bool(0.05 <= p_value < 0.10),
    )


def rolling_engle_granger(
    brent: pd.Series,
    wti: pd.Series,
    *,
    window: int = 120,
    step: int = 20,
) -> pd.DataFrame:
    """Slide the Engle-Granger test across the series.

    Returns a DataFrame with columns `window_end`, `p_value`,
    `hedge_ratio`, `verdict`, `half_life_days`. Useful for spotting
    structural-break regimes on the cointegration tile.
    """
    brent = brent.dropna()
    wti = wti.dropna()
    idx = brent.index.intersection(wti.index)
    if len(idx) < window + step:
        return pd.DataFrame(
            columns=["window_end", "p_value", "hedge_ratio", "verdict", "half_life_days"]
        )

    rows: list[dict[str, Any]] = []
    i = window
    while i <= len(idx):
        sub_idx = idx[i - window : i]
        res = engle_granger(brent.loc[sub_idx], wti.loc[sub_idx], min_obs=max(30, window // 2))
        rows.append(
            {
                "window_end": sub_idx[-1],
                "p_value": res.p_value,
                "hedge_ratio": res.hedge_ratio,
                "verdict": res.verdict,
                "half_life_days": res.half_life_days,
            }
        )
        i += step

    return pd.DataFrame(rows)


__all__ = [
    "CointegrationResult",
    "engle_granger",
    "rolling_engle_granger",
]
