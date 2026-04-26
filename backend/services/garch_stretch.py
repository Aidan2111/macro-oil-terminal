"""GARCH(1,1)-normalized stretch service.

The hero card already shows a "rolling-z" stretch (spread minus 90-day
mean over 90-day stdev). That stat under-counts vol clustering — when
the market is in a high-vol regime, |z| systematically over-reads.
Replacing the denominator with a GARCH(1,1) conditional sigma gives a
"true" sigma that reacts to regime change.

Public surface:
    compute_garch_normalized_stretch(spread_df) -> tuple[float, dict]
        returns (z, diagnostics)

The diagnostics dict carries:
    {
        "ok": bool,
        "sigma": float,              # latest conditional σ_t
        "persistence": float,        # α + β
        "fallback_used": bool,
        "fallback_reason": str,
        "n_obs": int,
    }

When the fit fails, ``ok`` is False, the rolling-std-based stretch is
returned as ``z`` (so the hero never blanks), and ``fallback_reason``
explains why (short window, arch-package missing, divergent fit).
The frontend's advanced toggle reads ``ok`` to decide whether to render
the GARCH badge or the "Fell back to rolling std" caveat.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Tuple

from . import _compat  # noqa: F401 — sets sys.path for legacy imports


_MIN_OBS = 100  # arch_model fits below this are wildly noisy; mirror vol_models.


def _rolling_z_fallback(spread_df: Any) -> float:
    """Read the existing rolling-std Z off the spread frame.

    ``compute_spread_zscore`` already populates a ``Z_Score`` column;
    pull the last finite value. If the column is missing or all-NaN
    we return 0.0 so the UI stays neutral instead of blanking.
    """
    try:
        import math as _math
        import pandas as pd  # type: ignore
    except Exception:  # pragma: no cover
        return 0.0
    if not isinstance(spread_df, pd.DataFrame) or spread_df.empty:
        return 0.0
    if "Z_Score" not in spread_df.columns:
        return 0.0
    series = spread_df["Z_Score"].dropna()
    if series.empty:
        return 0.0
    val = float(series.iloc[-1])
    if not _math.isfinite(val):
        return 0.0
    return val


def compute_garch_normalized_stretch(spread_df: Any) -> Tuple[float, Dict[str, Any]]:
    """Fit GARCH(1,1) on the residual stream and return (z, diagnostics).

    The residual is ``Spread − Spread_Mean`` (i.e. the same numerator
    the rolling-z uses). The denominator is the conditional σ from the
    GARCH fit on that residual stream. On any failure the rolling-z is
    returned as the fallback and ``ok=False`` is set.
    """
    try:
        import math as _math
        import numpy as np  # type: ignore
        import pandas as pd  # type: ignore
    except Exception as exc:  # pragma: no cover
        return 0.0, {
            "ok": False,
            "sigma": float("nan"),
            "persistence": float("nan"),
            "fallback_used": True,
            "fallback_reason": f"numpy/pandas unavailable: {exc!r}",
            "n_obs": 0,
        }

    if (
        spread_df is None
        or not isinstance(spread_df, pd.DataFrame)
        or spread_df.empty
        or "Spread" not in spread_df.columns
    ):
        return _rolling_z_fallback(spread_df), {
            "ok": False,
            "sigma": float("nan"),
            "persistence": float("nan"),
            "fallback_used": True,
            "fallback_reason": "missing Spread column",
            "n_obs": int(0 if spread_df is None else len(spread_df)),
        }

    spread = spread_df["Spread"].astype(float)
    if "Spread_Mean" in spread_df.columns:
        rolling_mean = spread_df["Spread_Mean"].astype(float)
    else:
        rolling_mean = spread.rolling(90, min_periods=30).mean()

    residual = (spread - rolling_mean).dropna()
    n = int(len(residual))

    if n < _MIN_OBS:
        return _rolling_z_fallback(spread_df), {
            "ok": False,
            "sigma": float("nan"),
            "persistence": float("nan"),
            "fallback_used": True,
            "fallback_reason": f"residual series too short (n={n}, need {_MIN_OBS})",
            "n_obs": n,
        }

    try:
        from vol_models import fit_garch_residual  # type: ignore
    except Exception as exc:  # pragma: no cover
        return _rolling_z_fallback(spread_df), {
            "ok": False,
            "sigma": float("nan"),
            "persistence": float("nan"),
            "fallback_used": True,
            "fallback_reason": f"vol_models unavailable: {exc!r}",
            "n_obs": n,
        }

    try:
        result = fit_garch_residual(residual, latest_value=float(residual.iloc[-1]))
    except Exception as exc:  # pragma: no cover — fit_garch_residual is itself defensive
        return _rolling_z_fallback(spread_df), {
            "ok": False,
            "sigma": float("nan"),
            "persistence": float("nan"),
            "fallback_used": True,
            "fallback_reason": f"fit raised: {exc!r}"[:200],
            "n_obs": n,
        }

    if not result.ok or not _math.isfinite(result.z):
        return _rolling_z_fallback(spread_df), {
            "ok": False,
            "sigma": float(result.sigma) if _math.isfinite(result.sigma) else float("nan"),
            "persistence": float(result.persistence) if _math.isfinite(result.persistence) else float("nan"),
            "fallback_used": True,
            "fallback_reason": result.note or "GARCH fit returned ok=False",
            "n_obs": n,
        }

    return float(result.z), {
        "ok": True,
        "sigma": float(result.sigma),
        "persistence": float(result.persistence),
        "fallback_used": False,
        "fallback_reason": "",
        "n_obs": n,
    }


__all__ = ["compute_garch_normalized_stretch"]
