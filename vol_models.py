"""GARCH(1,1) helper for a "true" vol-normalised dislocation.

The ``arch`` package provides the maximum-likelihood GARCH fit. We wrap
it defensively: if the fit diverges, the series is too short, or the
package isn't importable, we fall back to the EWMA σ already computed
in ``quantitative_models.compute_spread_zscore`` and surface the
failure through an ``ok=False`` flag so the UI can show a warning.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


try:
    from arch import arch_model
    _HAS_ARCH = True
except Exception:  # pragma: no cover
    arch_model = None  # type: ignore
    _HAS_ARCH = False


@dataclass
class GarchResult:
    ok: bool
    sigma: float                   # latest conditional standard deviation
    z: float                       # latest GARCH-normalised dislocation
    sigma_series: Optional[pd.Series]  # full conditional σ_t series
    persistence: float             # α+β, the "stickiness" of vol shocks
    note: str = ""                 # non-empty when ok=False, carries the reason


def fit_garch_residual(residual: pd.Series, *, latest_value: Optional[float] = None) -> GarchResult:
    """Fit GARCH(1,1) to a residual series and return the latest σ + z.

    ``latest_value`` defaults to the last residual point if not supplied,
    which is the most common use case (today's spread minus the rolling mean).
    """
    r = residual.dropna()
    last = float(latest_value) if latest_value is not None else (float(r.iloc[-1]) if len(r) else 0.0)

    if not _HAS_ARCH or len(r) < 100:
        return GarchResult(
            ok=False, sigma=float("nan"), z=float("nan"),
            sigma_series=None, persistence=float("nan"),
            note=("arch package missing" if not _HAS_ARCH else f"series too short (n={len(r)})"),
        )

    try:
        # rescale=False — the spread is already on a sensible scale; avoid
        # the arch warning about variance explosion.
        model = arch_model(r.values.astype(float), vol="GARCH", p=1, q=1, mean="Zero", rescale=False)
        fit = model.fit(disp="off", show_warning=False)
    except Exception as exc:
        return GarchResult(
            ok=False, sigma=float("nan"), z=float("nan"),
            sigma_series=None, persistence=float("nan"),
            note=f"fit failed: {exc!r}"[:200],
        )

    cond_vol = pd.Series(fit.conditional_volatility, index=r.index)
    sigma = float(cond_vol.iloc[-1])
    if sigma <= 0 or not np.isfinite(sigma):
        return GarchResult(
            ok=False, sigma=float("nan"), z=float("nan"),
            sigma_series=None, persistence=float("nan"),
            note="non-positive sigma",
        )
    z = float(last / sigma)
    alpha = float(fit.params.get("alpha[1]", 0.0))
    beta = float(fit.params.get("beta[1]", 0.0))
    persistence = float(alpha + beta)

    return GarchResult(
        ok=True, sigma=sigma, z=z,
        sigma_series=cond_vol,
        persistence=persistence,
        note="",
    )


__all__ = ["GarchResult", "fit_garch_residual"]
