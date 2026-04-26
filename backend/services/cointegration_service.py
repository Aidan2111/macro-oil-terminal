"""Cointegration service — Engle-Granger wrapper with content-hash cache.

Wraps the existing top-level ``cointegration.engle_granger`` helper so the
hot SSE path (``/api/thesis/generate`` rebuilds the context on every poll)
doesn't pay the OLS + ADF cost on every request. The cache key is a
SHA-256 over the (Brent, WTI) numeric content; identical price tapes are
hit in O(n) hash time and skip the regression entirely.

Public surface:
    compute_cointegration_for_thesis(spread_df) -> CointegrationStats

The returned dataclass intentionally exposes only what the hero card
renders + what the LLM should cite — full statsmodels output is not
re-emitted because we lock the wire shape early so the React types stay
stable across the merge-up.

Failure semantics — never raise:
    * series too short / NaN-saturated         → message="series too short"
    * statsmodels missing / fit divergence     → message="solver failed"
    * spread_df missing the required columns   → message="missing columns"

In every failure case, ``eg_pvalue`` and ``half_life_days`` are ``nan``
and the hero card renders the inconclusive state. The LLM also sees the
``message`` and is instructed (system prompt) to flag it as a data
caveat rather than fabricate a verdict.
"""

from __future__ import annotations

import hashlib
import math
import threading
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

from . import _compat  # noqa: F401 — sets sys.path for legacy imports


# ---------------------------------------------------------------------------
# Public dataclass — pinned schema, cached on the hash of input data
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class CointegrationStats:
    eg_pvalue: float                       # Engle-Granger ADF p-value on residual; NaN ⇒ inconclusive
    half_life_days: float                  # OU half-life in days; NaN ⇒ unit-root / inconclusive
    johansen_trace: Optional[float]        # reserved — currently None; wired in a follow-up
    hedge_ratio: float                     # β from Brent = α + β·WTI; NaN on failure
    verdict: str                           # "cointegrated" | "weak" | "not_cointegrated" | "inconclusive"
    n_obs: int
    message: str                           # human-readable status. "" on the happy path.

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # JSON cannot serialise NaN — clamp to None so FastAPI's default
        # encoder doesn't emit "NaN" tokens that some clients reject.
        for k in ("eg_pvalue", "half_life_days", "hedge_ratio"):
            v = d[k]
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                d[k] = None
        return d


# ---------------------------------------------------------------------------
# Content-hash cache (process-local)
# ---------------------------------------------------------------------------
# Keep it tiny on purpose — for the SSE poll cycle a single slot is enough.
# A larger cache here would hold pandas frames in memory longer than needed.
_CACHE: Dict[str, CointegrationStats] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_MAX = 16


def _content_hash(df: Any) -> Optional[str]:
    """SHA-256 over the Brent + WTI numeric content + index range.

    We hash bytes derived from the underlying numpy arrays so the same
    closing prices on the same dates always hit. NaN bytes are stable.
    Returns None when we can't form a sensible key — caller will skip
    the cache and recompute.
    """
    try:
        import numpy as np  # type: ignore
        import pandas as pd  # type: ignore
    except Exception:  # pragma: no cover
        return None
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return None
    if "Brent" not in df.columns or "WTI" not in df.columns:
        return None
    h = hashlib.sha256()
    try:
        b = np.asarray(df["Brent"].values, dtype=float)
        w = np.asarray(df["WTI"].values, dtype=float)
        h.update(b.tobytes())
        h.update(w.tobytes())
        # Encode the index footprint too — same prices on different dates
        # is technically a different sample.
        h.update(str(df.index.min()).encode())
        h.update(str(df.index.max()).encode())
        h.update(str(len(df)).encode())
    except Exception:
        return None
    return h.hexdigest()


def _cache_get(key: Optional[str]) -> Optional[CointegrationStats]:
    if key is None:
        return None
    with _CACHE_LOCK:
        return _CACHE.get(key)


def _cache_put(key: Optional[str], value: CointegrationStats) -> None:
    if key is None:
        return
    with _CACHE_LOCK:
        if len(_CACHE) >= _CACHE_MAX:
            # FIFO eviction — drop the oldest entry. dict preserves insert
            # order in 3.7+, so we pop the first key.
            try:
                first = next(iter(_CACHE))
                _CACHE.pop(first, None)
            except StopIteration:
                pass
        _CACHE[key] = value


def cache_clear() -> None:
    """Drop every cached cointegration result. Test-only helper."""
    with _CACHE_LOCK:
        _CACHE.clear()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def compute_cointegration_for_thesis(spread_df: Any) -> CointegrationStats:
    """Run Engle-Granger on the (Brent, WTI) pair embedded in ``spread_df``.

    ``spread_df`` is the same DataFrame produced by
    ``quantitative_models.compute_spread_zscore`` — it carries Brent + WTI
    columns alongside the rolling stretch.

    On failure / inconclusive input we return a populated dataclass with
    ``message`` set rather than raising; the hero card surfaces the
    inconclusive pill in that case.
    """
    key = _content_hash(spread_df)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    # Validate shape upfront — gives a clean message instead of an opaque
    # KeyError from inside cointegration.engle_granger.
    try:
        import pandas as pd  # type: ignore
    except Exception as exc:  # pragma: no cover
        out = CointegrationStats(
            eg_pvalue=float("nan"),
            half_life_days=float("nan"),
            johansen_trace=None,
            hedge_ratio=float("nan"),
            verdict="inconclusive",
            n_obs=0,
            message=f"pandas unavailable: {exc!r}",
        )
        _cache_put(key, out)
        return out

    if (
        spread_df is None
        or not isinstance(spread_df, pd.DataFrame)
        or spread_df.empty
        or "Brent" not in spread_df.columns
        or "WTI" not in spread_df.columns
    ):
        out = CointegrationStats(
            eg_pvalue=float("nan"),
            half_life_days=float("nan"),
            johansen_trace=None,
            hedge_ratio=float("nan"),
            verdict="inconclusive",
            n_obs=int(0 if spread_df is None else len(spread_df)),
            message="missing Brent/WTI columns",
        )
        _cache_put(key, out)
        return out

    try:
        from cointegration import engle_granger  # type: ignore
    except Exception as exc:  # pragma: no cover
        out = CointegrationStats(
            eg_pvalue=float("nan"),
            half_life_days=float("nan"),
            johansen_trace=None,
            hedge_ratio=float("nan"),
            verdict="inconclusive",
            n_obs=int(len(spread_df)),
            message=f"cointegration module unavailable: {exc!r}",
        )
        _cache_put(key, out)
        return out

    try:
        result = engle_granger(spread_df["Brent"], spread_df["WTI"])
    except Exception as exc:  # pragma: no cover — engle_granger is itself defensive
        out = CointegrationStats(
            eg_pvalue=float("nan"),
            half_life_days=float("nan"),
            johansen_trace=None,
            hedge_ratio=float("nan"),
            verdict="inconclusive",
            n_obs=int(len(spread_df)),
            message=f"solver failed: {exc!r}"[:200],
        )
        _cache_put(key, out)
        return out

    half_life = result.half_life_days
    half_life_f = float(half_life) if half_life is not None else float("nan")
    message = ""
    if result.verdict == "inconclusive":
        message = f"too few observations (n={result.n_obs})"

    out = CointegrationStats(
        eg_pvalue=float(result.p_value),
        half_life_days=half_life_f,
        johansen_trace=None,  # reserved
        hedge_ratio=float(result.hedge_ratio),
        verdict=str(result.verdict),
        n_obs=int(result.n_obs),
        message=message,
    )
    _cache_put(key, out)
    return out


__all__ = [
    "CointegrationStats",
    "compute_cointegration_for_thesis",
    "cache_clear",
]
