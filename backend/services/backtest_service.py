"""Backtest service — Z-score mean-reversion wrapper.

Thin adapter over ``quantitative_models.backtest_zscore_meanreversion``.
Fetches the spread series (Brent–WTI) either from an injected DataFrame
(tests) or from the live cointegration module (production), then calls the
backtester and shapes the result into a JSON-friendly dict the Next.js
frontend can render directly.

The frontend chart needs ``equity_curve`` as ``list[{date, cum_pnl_usd}]``
and ``trades`` as ``list[dict]`` with ISO dates — we convert pandas objects
here so the router never has to touch pandas.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from . import _compat  # noqa: F401 — sets sys.path for legacy imports


def _backtest_zscore_meanreversion(
    spread_df: Any,
    *,
    entry_z: float,
    exit_z: float,
    slippage_per_bbl: float,
    commission_per_trade: float,
) -> dict:
    """Lazy wrapper around ``quantitative_models.backtest_zscore_meanreversion``.

    Lazy import keeps sklearn + pandas out of the module-import graph for
    tests that don't exercise the backtest path.
    """
    import quantitative_models  # type: ignore

    return quantitative_models.backtest_zscore_meanreversion(
        spread_df,
        entry_z=entry_z,
        exit_z=exit_z,
        slippage_per_bbl=slippage_per_bbl,
        commission_per_trade=commission_per_trade,
    )


def _load_spread_df(lookback_days: int) -> Any:
    """Return a spread DataFrame with ``Spread`` + ``Z_Score`` columns.

    In production this delegates to the legacy ``cointegration.build_spread``
    (or similar) helper. We try a few common names so Sub-A's richer shim can
    override cleanly on merge-up without this file needing to change again.
    """
    import pathlib
    import sys

    # _compat already put the repo root on sys.path; belt-and-braces here so
    # tests that only import this module still work.
    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    try:
        import cointegration  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "cointegration module unavailable — cannot build spread series"
        ) from exc

    for attr in ("build_spread_df", "compute_spread_series", "build_spread"):
        fn = getattr(cointegration, attr, None)
        if callable(fn):
            # Most of these helpers accept an optional lookback/days param.
            try:
                return fn(lookback_days=lookback_days)
            except TypeError:
                try:
                    return fn(lookback_days)
                except TypeError:
                    return fn()

    raise RuntimeError(
        "cointegration has no build_spread_df()/compute_spread_series() entry"
    )


def _jsonable(value: Any) -> Any:
    """Recursively coerce pandas / numpy / NaN / Timestamp into JSON scalars."""
    try:
        import numpy as np  # type: ignore
        import pandas as pd  # type: ignore
    except Exception:  # pragma: no cover — deps enforced by requirements.txt
        np = None  # type: ignore
        pd = None  # type: ignore

    if value is None:
        return None
    if pd is not None and isinstance(value, pd.Timestamp):
        return value.isoformat()
    if pd is not None and isinstance(value, pd.DataFrame):
        return [_jsonable(r) for r in value.to_dict(orient="records")]
    if pd is not None and isinstance(value, pd.Series):
        return [_jsonable(v) for v in value.tolist()]
    if np is not None and isinstance(value, (np.integer,)):
        return int(value)
    if np is not None and isinstance(value, (np.floating,)):
        f = float(value)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def run_backtest(
    *,
    entry_z: float,
    exit_z: float,
    lookback_days: int,
    slippage_per_bbl: float,
    commission_per_trade: float,
    spread_df: Optional[Any] = None,
) -> dict:
    """Run the Z-score mean-reversion backtest and return a JSON-safe dict.

    Output keys:
        ``sharpe`` / ``sortino`` / ``calmar`` / ``var_95`` / ``es_95`` /
        ``max_drawdown`` / ``hit_rate`` / ``total_pnl_usd`` / ``n_trades`` /
        ``avg_days_held`` / ``avg_pnl_per_bbl`` / ``rolling_12m_sharpe`` /
        ``equity_curve`` (list) / ``trades`` (list) /
        ``params`` (echo of the request).
    """
    if spread_df is None:
        spread_df = _load_spread_df(lookback_days)

    raw = _backtest_zscore_meanreversion(
        spread_df,
        entry_z=entry_z,
        exit_z=exit_z,
        slippage_per_bbl=slippage_per_bbl,
        commission_per_trade=commission_per_trade,
    )

    # Issue #94 — surface bootstrap 95% CIs on every metric the
    # frontend renders so the reader can see the sampling-noise
    # envelope around the headline numbers. Best-effort: an empty
    # ``trades`` blotter or a sub-5-trade sample skips this block.
    metric_cis: dict = {}
    try:
        import quantitative_models  # type: ignore

        metric_cis = quantitative_models.bootstrap_metric_cis(
            raw.get("trades"), n_resamples=1000, confidence=0.95
        )
    except Exception:
        metric_cis = {}

    equity_curve = _jsonable(raw.get("equity_curve"))
    trades = _jsonable(raw.get("trades"))

    return {
        "sharpe": _jsonable(raw.get("sharpe", 0.0)),
        "sortino": _jsonable(raw.get("sortino", 0.0)),
        "calmar": _jsonable(raw.get("calmar", 0.0)),
        "var_95": _jsonable(raw.get("var_95", 0.0)),
        "es_95": _jsonable(raw.get("es_95", 0.0)),
        # Q3 prediction-quality slice — desk-grade tail metric.
        "es_975": _jsonable(raw.get("es_975", 0.0)),
        "max_drawdown": _jsonable(raw.get("max_drawdown_usd", 0.0)),
        "hit_rate": _jsonable(raw.get("win_rate", 0.0)),
        "total_pnl_usd": _jsonable(raw.get("total_pnl_usd", 0.0)),
        "n_trades": int(raw.get("n_trades", 0) or 0),
        "avg_days_held": _jsonable(raw.get("avg_days_held", 0.0)),
        "avg_pnl_per_bbl": _jsonable(raw.get("avg_pnl_per_bbl", 0.0)),
        "rolling_12m_sharpe": _jsonable(raw.get("rolling_12m_sharpe")),
        "equity_curve": equity_curve or [],
        "trades": trades or [],
        "metric_cis": _jsonable(metric_cis),
        "params": {
            "entry_z": entry_z,
            "exit_z": exit_z,
            "lookback_days": lookback_days,
            "slippage_per_bbl": slippage_per_bbl,
            "commission_per_trade": commission_per_trade,
        },
    }


__all__ = ["run_backtest"]
