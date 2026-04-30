"""Quantitative logic for the oil-terminal dashboard.

Three public helpers:
  * compute_spread_zscore   – daily Brent-WTI spread + rolling 90d Z
  * forecast_depletion      – LinearRegression on trailing N weeks
  * categorize_flag_states  – aggregate cargo by policy category
"""

from __future__ import annotations

from datetime import timedelta
from typing import Dict, Tuple

import math

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression


# ---------------------------------------------------------------------------
# Spread & Z-score
# ---------------------------------------------------------------------------
def compute_spread_zscore(prices: pd.DataFrame, window: int = 90) -> pd.DataFrame:
    """Return a DataFrame with Brent, WTI, Spread and rolling Z-score columns.

    The Z-score is ``(spread - rolling_mean) / rolling_std`` over ``window``
    trading days. Rows with a still-NaN Z (first ``window-1`` observations)
    are retained so the user can see the warm-up period.

    Also computes an **EWMA-of-squared-residuals** volatility proxy
    (λ=0.94, the RiskMetrics default) and a *vol-normalised* dislocation
    ``Z_Vol`` alongside the classic rolling-std version. ``Z_Vol`` is
    what a desk quant would call "the real sigma" — it reacts to regime
    change faster than the fixed-window rolling std.
    """
    if prices is None or prices.empty:
        return pd.DataFrame(
            columns=[
                "Brent", "WTI", "Spread",
                "Spread_Mean", "Spread_Std", "Z_Score",
                "Spread_EwmaStd", "Z_Vol",
            ]
        )

    df = prices.copy()
    if "Brent" not in df.columns or "WTI" not in df.columns:
        raise ValueError("prices must contain 'Brent' and 'WTI' columns")

    df["Spread"] = df["Brent"] - df["WTI"]
    # Shift by one bar BEFORE the rolling window so the mean/std at bar t
    # are computed from the closed interval [t-W, t-1] — i.e. information
    # a trader would actually know at the close of bar t, not including
    # spread[t] itself. Without this shift, the Z at bar t is contaminated
    # by its own value (same-bar look-ahead) and |Z| shrinks on exactly
    # the bar the backtest transacts on. See Persona 01 Finding #1 and
    # synthesis Row 1. Equivalent to ``.rolling(window=window, closed="left")``
    # but the shift(1) form is more portable across pandas versions.
    min_p = max(5, window // 3)
    shifted_spread = df["Spread"].shift(1)
    df["Spread_Mean"] = shifted_spread.rolling(window=window, min_periods=min_p).mean()
    df["Spread_Std"] = shifted_spread.rolling(window=window, min_periods=min_p).std()
    std_safe = df["Spread_Std"].replace(0, np.nan)
    df["Z_Score"] = (df["Spread"] - df["Spread_Mean"]) / std_safe
    df["Z_Score"] = df["Z_Score"].replace([np.inf, -np.inf], np.nan)

    # EWMA variance on residuals (spread − rolling mean). λ=0.94 is the
    # RiskMetrics convention for daily equity returns; it's reasonable for
    # a daily spread too. Mirror the shift(1) semantics on the residual
    # stream so the ewm variance at bar t does not include residual[t] —
    # otherwise the same same-bar look-ahead bias leaks into Z_Vol.
    resid = (df["Spread"] - df["Spread_Mean"]).shift(1)
    ewm_var = (resid ** 2).ewm(alpha=1 - 0.94, min_periods=10, adjust=False).mean()
    df["Spread_EwmaStd"] = np.sqrt(ewm_var)
    ewm_std_safe = df["Spread_EwmaStd"].replace(0, np.nan)
    df["Z_Vol"] = (df["Spread"] - df["Spread_Mean"]) / ewm_std_safe
    df["Z_Vol"] = df["Z_Vol"].replace([np.inf, -np.inf], np.nan)

    return df


# ---------------------------------------------------------------------------
# Depletion forecaster
# ---------------------------------------------------------------------------
def forecast_depletion(
    inventory: pd.DataFrame,
    floor_bbls: float = 300_000_000.0,
    lookback_weeks: int = 4,
) -> Dict[str, object]:
    """Fit a LinearRegression to the trailing ``lookback_weeks`` of inventory.

    Returns a dict:
      {
        "daily_depletion_bbls":  float,            # negative => drawdown
        "weekly_depletion_bbls": float,
        "projected_floor_date":  pd.Timestamp | None,
        "regression_line":       pd.DataFrame(Date, Projected_Inventory_bbls),
        "r_squared":             float,
        "current_inventory":     float,
        "floor_bbls":            float,
      }
    """
    out = {
        "daily_depletion_bbls": 0.0,
        "weekly_depletion_bbls": 0.0,
        "projected_floor_date": None,
        "regression_line": pd.DataFrame(columns=["Date", "Projected_Inventory_bbls"]),
        "r_squared": 0.0,
        "current_inventory": float("nan"),
        "floor_bbls": float(floor_bbls),
    }

    if inventory is None or inventory.empty:
        return out
    if "Total_Inventory_bbls" not in inventory.columns:
        raise ValueError("inventory must contain 'Total_Inventory_bbls' column")

    lookback_weeks = max(2, int(lookback_weeks))
    series = inventory["Total_Inventory_bbls"].dropna()
    if len(series) < 2:
        return out

    trail = series.tail(lookback_weeks)
    if len(trail) < 2:
        trail = series.tail(max(2, len(series)))

    # X = days since first obs in the trailing window
    t0 = trail.index.min()
    x_days = np.array([(d - t0).days for d in trail.index], dtype=float).reshape(-1, 1)
    y = trail.values.astype(float)

    model = LinearRegression().fit(x_days, y)
    slope_per_day = float(model.coef_[0])  # bbls/day
    intercept = float(model.intercept_)
    r2 = float(model.score(x_days, y))

    out["daily_depletion_bbls"] = slope_per_day
    out["weekly_depletion_bbls"] = slope_per_day * 7.0
    out["r_squared"] = r2
    out["current_inventory"] = float(series.iloc[-1])

    # Projected date when inventory breaches the floor
    # inventory(t) = intercept + slope * t_days   (t_days measured from t0)
    projected_date = None
    if slope_per_day < 0:
        days_to_floor = (floor_bbls - intercept) / slope_per_day
        if np.isfinite(days_to_floor) and days_to_floor > 0:
            projected_date = pd.Timestamp(t0) + timedelta(days=float(days_to_floor))
    out["projected_floor_date"] = projected_date

    # Regression line: extend from window start through either the projected
    # floor date or a 2-year horizon, whichever is earlier.
    last_obs = trail.index.max()
    horizon_end = pd.Timestamp(t0) + timedelta(days=365 * 3)
    end_date = projected_date if projected_date is not None else horizon_end
    end_date = min(end_date, horizon_end)
    if end_date <= last_obs:
        end_date = last_obs + timedelta(days=180)

    proj_idx = pd.date_range(start=t0, end=end_date, freq="W-FRI")
    if len(proj_idx) < 2:
        proj_idx = pd.date_range(start=t0, end=end_date, freq="D")
    proj_days = np.array([(d - t0).days for d in proj_idx], dtype=float).reshape(-1, 1)
    proj_vals = model.predict(proj_days)

    out["regression_line"] = pd.DataFrame(
        {"Date": proj_idx, "Projected_Inventory_bbls": proj_vals}
    ).reset_index(drop=True)

    return out


# ---------------------------------------------------------------------------
# Flag-state categorization
# ---------------------------------------------------------------------------
_JONES_ACT_FLAGS = {"United States", "USA", "US"}
_SHADOW_FLAGS = {"Panama", "Liberia", "Marshall Islands", "Malta"}
_SANCTIONED_FLAGS = {"Russia", "Iran", "Venezuela"}


def _categorize_row(flag: str, destination: str) -> str:
    flag = (flag or "").strip()
    destination = (destination or "").strip()
    dest_is_us = destination.endswith("US") or ", US" in destination or "USA" in destination
    if flag in _JONES_ACT_FLAGS or dest_is_us:
        return "Jones Act / Domestic"
    if flag in _SANCTIONED_FLAGS:
        return "Sanctioned"
    if flag in _SHADOW_FLAGS:
        return "Shadow Risk"
    return "Other"


def categorize_flag_states(ais_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Return ``(detailed_df, aggregated_df)``.

    ``detailed_df`` is the input with a new ``Category`` column.
    ``aggregated_df`` sums ``Cargo_Volume_bbls`` by category (in millions of bbls)
    and always includes the three headline categories even if they are empty.
    """
    if ais_df is None or ais_df.empty:
        empty = pd.DataFrame(
            {
                "Category": ["Jones Act / Domestic", "Shadow Risk", "Sanctioned"],
                "Total_Cargo_Mbbl": [0.0, 0.0, 0.0],
                "Vessel_Count": [0, 0, 0],
            }
        )
        return ais_df if ais_df is not None else pd.DataFrame(), empty

    df = ais_df.copy()
    if "Flag_State" not in df.columns or "Destination" not in df.columns:
        raise ValueError("AIS dataframe must contain Flag_State and Destination columns")
    if "Cargo_Volume_bbls" not in df.columns:
        raise ValueError("AIS dataframe must contain Cargo_Volume_bbls column")

    df["Category"] = [
        _categorize_row(f, d) for f, d in zip(df["Flag_State"], df["Destination"])
    ]

    grouped = (
        df.groupby("Category")
        .agg(
            Total_Cargo_bbls=("Cargo_Volume_bbls", "sum"),
            Vessel_Count=("Cargo_Volume_bbls", "count"),
        )
        .reset_index()
    )
    grouped["Total_Cargo_Mbbl"] = grouped["Total_Cargo_bbls"] / 1_000_000.0

    # Ensure the three headline categories always appear in a consistent order
    preferred_order = ["Jones Act / Domestic", "Shadow Risk", "Sanctioned", "Other"]
    for cat in preferred_order:
        if cat not in grouped["Category"].values:
            grouped = pd.concat(
                [
                    grouped,
                    pd.DataFrame(
                        {
                            "Category": [cat],
                            "Total_Cargo_bbls": [0.0],
                            "Vessel_Count": [0],
                            "Total_Cargo_Mbbl": [0.0],
                        }
                    ),
                ],
                ignore_index=True,
            )
    grouped["__order"] = grouped["Category"].map({c: i for i, c in enumerate(preferred_order)})
    grouped = grouped.sort_values("__order").drop(columns="__order").reset_index(drop=True)

    return df, grouped


# ---------------------------------------------------------------------------
# Backtest — Z-score mean-reversion on the Brent-WTI spread
# ---------------------------------------------------------------------------
def backtest_zscore_meanreversion(
    spread_df: pd.DataFrame,
    entry_z: float = 2.0,
    exit_z: float = 0.2,
    notional_bbls: float = 10_000.0,
    slippage_per_bbl: float = 0.0,
    commission_per_trade: float = 0.0,
) -> Dict[str, object]:
    """Rule-based backtest of the classic spread mean-reversion play.

    Rule:
      * Enter **short spread** (short Brent / long WTI) when Z >=  entry_z
      * Enter **long spread**  (long  Brent / short WTI) when Z <= -entry_z
      * Exit flat on the next bar where ``abs(Z) <= exit_z``

    Returns a dict containing the per-trade DataFrame and summary stats
    (win rate, total PnL, Sharpe-ish). Spread PnL is measured per barrel.
    """
    empty = pd.DataFrame(
        columns=[
            "entry_date", "exit_date", "side", "entry_spread",
            "exit_spread", "pnl_per_bbl", "pnl_usd", "days_held",
        ]
    )
    out = {
        "trades": empty,
        "total_pnl_usd": 0.0,
        "n_trades": 0,
        "win_rate": 0.0,
        "avg_days_held": 0.0,
        "avg_pnl_per_bbl": 0.0,
        "equity_curve": pd.DataFrame(columns=["Date", "cum_pnl_usd"]),
        "max_drawdown_usd": 0.0,
        "sharpe": 0.0,
        "sortino": 0.0,
        "calmar": 0.0,
        "var_95": 0.0,
        "es_95": 0.0,
        # Q3 prediction-quality slice — Expected Shortfall at the 97.5%
        # confidence level (i.e. the average loss in the worst 2.5% of
        # trades). The 95% ES already lived here; 97.5 is the desk-grade
        # tail metric the risk-team review specifically called for.
        "es_975": 0.0,
        "rolling_12m_sharpe": float("nan"),
    }

    if spread_df is None or spread_df.empty:
        return out
    if "Z_Score" not in spread_df.columns or "Spread" not in spread_df.columns:
        return out

    df = spread_df[["Spread", "Z_Score"]].dropna().copy()
    if df.empty:
        return out

    trades: list[dict] = []
    position = 0  # +1 long spread, -1 short spread, 0 flat
    entry_date = None
    entry_spread = 0.0

    # After Row 1, the Z at bar t is computed from spread[t-W .. t-1] — it
    # is known at close-of-t. We transact at close-of-t's Spread, which is
    # also known at that instant, so the pairing is now legitimate. A
    # stricter "fill at next open" model (Row 23 / synthesis Row 3 / 10)
    # is deliberately NOT in scope for this branch — that's its own fix.
    for date, row in df.iterrows():
        z = float(row["Z_Score"])
        s = float(row["Spread"])
        if position == 0:
            if z >= entry_z:
                position = -1  # short spread
                entry_date, entry_spread = date, s
            elif z <= -entry_z:
                position = 1   # long spread
                entry_date, entry_spread = date, s
        else:
            if abs(z) <= exit_z:
                side = "long_spread" if position == 1 else "short_spread"
                gross_per_bbl = (s - entry_spread) * position
                # Slippage applied at both legs of the round-trip
                net_per_bbl = gross_per_bbl - 2.0 * float(slippage_per_bbl)
                pnl_usd = net_per_bbl * notional_bbls - 2.0 * float(commission_per_trade)
                trades.append(
                    {
                        "entry_date": entry_date,
                        "exit_date": date,
                        "side": side,
                        "entry_spread": entry_spread,
                        "exit_spread": s,
                        "pnl_per_bbl": float(net_per_bbl),
                        "pnl_usd": float(pnl_usd),
                        "days_held": (date - entry_date).days,
                    }
                )
                position = 0
                entry_date, entry_spread = None, 0.0

    tdf = pd.DataFrame(trades) if trades else empty

    if not tdf.empty:
        total = float(tdf["pnl_usd"].sum())
        wins = int((tdf["pnl_usd"] > 0).sum())
        eq = tdf.sort_values("exit_date").copy()
        eq["cum_pnl_usd"] = eq["pnl_usd"].cumsum()
        equity = eq.rename(columns={"exit_date": "Date"})[["Date", "cum_pnl_usd"]]

        # Max drawdown (peak-to-trough on cumulative PnL)
        running_max = equity["cum_pnl_usd"].cummax()
        drawdown = equity["cum_pnl_usd"] - running_max
        max_dd = float(drawdown.min()) if not drawdown.empty else 0.0

        # Sharpe-ish ratio: mean trade PnL / stdev, annualised by sqrt(trades/yr).
        # Trades are irregularly spaced so we approximate annualisation by
        # sqrt(365 / mean_hold_days).
        pnl_series = tdf["pnl_usd"].astype(float)
        mean_hold = float(tdf["days_held"].mean()) or 1.0
        trades_per_year = 365.0 / max(mean_hold, 1.0)
        sharpe = float(
            (pnl_series.mean() / pnl_series.std(ddof=0)) * np.sqrt(trades_per_year)
        ) if pnl_series.std(ddof=0) > 0 else 0.0

        # --- Desk-grade risk metrics (Sortino, Calmar, VaR-95, ES-95,
        # rolling-12m Sharpe on trade PnL series).
        # Downside-only stdev (Sortino denominator): stdev of negative returns
        neg = pnl_series[pnl_series < 0]
        downside_std = float(neg.std(ddof=0)) if len(neg) > 1 else 0.0
        sortino = float(
            (pnl_series.mean() / downside_std) * np.sqrt(trades_per_year)
        ) if downside_std > 0 else float("inf") if pnl_series.mean() > 0 else 0.0

        # Calmar = annualised total return / |max drawdown|
        years = max(
            1.0 / 12.0,
            (tdf["exit_date"].max() - tdf["entry_date"].min()).days / 365.25,
        )
        ann_return = total / years
        calmar = float(ann_return / abs(max_dd)) if max_dd < 0 else float("inf")

        # Historical VaR / ES via numpy quantile (linear interpolation),
        # which gives smoothly-distinct values on small blotters where the
        # earlier integer-index recipe collapsed all three to the worst
        # single trade.  See issue #64.
        #
        # Definitions on the per-trade PnL distribution (negative = loss):
        #   var_95 = 5th-percentile single-trade outcome
        #   es_95  = mean of trades at or below var_95
        #   es_975 = mean of trades at or below the 2.5th-percentile cutoff
        #
        # On a non-degenerate distribution: |VaR-95| ≤ |ES-95| ≤ |ES-97.5|
        # because the ES tail averages strictly worse outcomes.
        pnl_arr = pnl_series.to_numpy(dtype=float)
        if pnl_arr.size:
            var95 = float(np.quantile(pnl_arr, 0.05))
            cutoff_975 = float(np.quantile(pnl_arr, 0.025))
            tail_95 = pnl_arr[pnl_arr <= var95]
            tail_975 = pnl_arr[pnl_arr <= cutoff_975]
            # tail arrays cannot be empty (the cutoff observation itself
            # always satisfies the <= predicate), but guard anyway.
            es95 = float(tail_95.mean()) if tail_95.size else var95
            es975 = float(tail_975.mean()) if tail_975.size else cutoff_975
        else:
            var95 = 0.0
            es95 = 0.0
            es975 = 0.0

        # Rolling 12-month Sharpe (window = trades fitting in ~365 days)
        rolling_sharpe_last = float("nan")
        if len(tdf) >= 6:
            tdf_sorted = tdf.sort_values("exit_date").reset_index(drop=True)
            pnl_by_date = tdf_sorted["pnl_usd"]
            w = max(3, int(round(trades_per_year)))
            rolling_mean = pnl_by_date.rolling(w).mean()
            rolling_std = pnl_by_date.rolling(w).std(ddof=0)
            rolling_sharpe = (rolling_mean / rolling_std.replace(0, np.nan)) * np.sqrt(trades_per_year)
            if rolling_sharpe.dropna().shape[0]:
                rolling_sharpe_last = float(rolling_sharpe.dropna().iloc[-1])

        out.update(
            {
                "trades": tdf.sort_values("entry_date").reset_index(drop=True),
                "total_pnl_usd": total,
                "n_trades": int(len(tdf)),
                "win_rate": wins / len(tdf),
                "avg_days_held": float(tdf["days_held"].mean()),
                "avg_pnl_per_bbl": float(tdf["pnl_per_bbl"].mean()),
                "equity_curve": equity.reset_index(drop=True),
                "max_drawdown_usd": max_dd,
                "sharpe": sharpe,
                "sortino": sortino,
                "calmar": calmar,
                "var_95": var95,
                "es_95": es95,
                "es_975": es975,
                "rolling_12m_sharpe": rolling_sharpe_last,
            }
        )
    else:
        out.update({
            "max_drawdown_usd": 0.0, "sharpe": 0.0,
            "sortino": 0.0, "calmar": 0.0,
            "var_95": 0.0, "es_95": 0.0, "es_975": 0.0,
            "rolling_12m_sharpe": float("nan"),
        })

    return out


# ---------------------------------------------------------------------------
# Walk-forward rolling window — parameter-stability diagnostic
# ---------------------------------------------------------------------------
def walk_forward_backtest(
    spread_df: pd.DataFrame,
    entry_z: float = 2.0,
    exit_z: float = 0.2,
    notional_bbls: float = 10_000.0,
    slippage_per_bbl: float = 0.0,
    window_months: int = 12,
    step_months: int = 3,
) -> pd.DataFrame:
    """Slide a rolling backtest window across the full history.

    Returns a DataFrame with one row per window containing the
    aggregate stats from ``backtest_zscore_meanreversion`` on that slice.
    Useful for spotting regimes where the signal breaks down.
    """
    if spread_df is None or spread_df.empty or "Z_Score" not in spread_df.columns:
        return pd.DataFrame(columns=["window_start", "window_end", "n_trades", "win_rate", "sharpe", "total_pnl_usd"])

    df = spread_df.dropna(subset=["Z_Score"])
    if df.empty:
        return pd.DataFrame()

    start = df.index.min()
    end = df.index.max()
    window = pd.DateOffset(months=window_months)
    step = pd.DateOffset(months=step_months)

    rows = []
    cursor = start
    while cursor + window <= end:
        left = cursor
        right = cursor + window
        sl = df.loc[left:right]
        if sl.empty:
            cursor = cursor + step
            continue
        out = backtest_zscore_meanreversion(
            sl, entry_z=entry_z, exit_z=exit_z,
            notional_bbls=notional_bbls, slippage_per_bbl=slippage_per_bbl,
        )
        rows.append(
            {
                "window_start": left,
                "window_end": right,
                "n_trades": out["n_trades"],
                "win_rate": out["win_rate"],
                "sharpe": out.get("sharpe", 0.0),
                "total_pnl_usd": out["total_pnl_usd"],
            }
        )
        cursor = cursor + step
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Monte Carlo — random-entry noise as a robustness check
# ---------------------------------------------------------------------------
def monte_carlo_entry_noise(
    spread_df: pd.DataFrame,
    entry_z: float = 2.0,
    exit_z: float = 0.2,
    notional_bbls: float = 10_000.0,
    slippage_per_bbl: float = 0.0,
    n_runs: int = 200,
    noise_sigma: float = 0.15,
    seed: int = 7,
) -> Dict[str, float]:
    """Perturb the entry threshold by i.i.d. Normal noise ``n_runs`` times.

    The idea: if a tiny wobble in ``entry_z`` changes total PnL
    dramatically, the strategy is overfit to a specific threshold.
    Returns summary stats of the PnL distribution.
    """
    if spread_df is None or spread_df.empty or "Z_Score" not in spread_df.columns:
        return {"n_runs": 0, "pnl_mean": 0.0, "pnl_std": 0.0, "pnl_p05": 0.0, "pnl_p95": 0.0}

    rng = np.random.default_rng(seed)
    results: list[float] = []
    for _ in range(n_runs):
        shift = float(rng.normal(0, noise_sigma))
        out = backtest_zscore_meanreversion(
            spread_df,
            entry_z=max(0.1, entry_z + shift),
            exit_z=exit_z,
            notional_bbls=notional_bbls,
            slippage_per_bbl=slippage_per_bbl,
        )
        results.append(float(out["total_pnl_usd"]))
    arr = np.array(results, dtype=float)
    return {
        "n_runs": len(arr),
        "pnl_mean": float(arr.mean()),
        "pnl_std": float(arr.std(ddof=0)),
        "pnl_p05": float(np.percentile(arr, 5)),
        "pnl_p95": float(np.percentile(arr, 95)),
    }


# ---------------------------------------------------------------------------
# Regime breakdown (high-vol vs low-vol)
# ---------------------------------------------------------------------------
def regime_breakdown(
    spread_df: pd.DataFrame,
    trades: pd.DataFrame,
    vol_window: int = 30,
) -> pd.DataFrame:
    """Split the trade blotter by the vol regime at trade entry.

    Returns a DataFrame with one row per regime (`low_vol`, `high_vol`)
    giving trade count, win rate, and total PnL.
    """
    if trades is None or trades.empty or spread_df is None or spread_df.empty:
        return pd.DataFrame(columns=["regime", "n_trades", "win_rate", "total_pnl_usd"])

    spread = spread_df["Spread"] if "Spread" in spread_df.columns else spread_df.iloc[:, 0]
    rolling_vol = spread.diff().rolling(vol_window).std()
    median_vol = float(rolling_vol.median())

    t = trades.copy()
    entry_vol = rolling_vol.reindex(t["entry_date"]).ffill().values
    t["regime"] = np.where(entry_vol > median_vol, "high_vol", "low_vol")

    grouped = (
        t.groupby("regime")
        .agg(
            n_trades=("pnl_usd", "count"),
            win_rate=("pnl_usd", lambda s: float((s > 0).mean()) if len(s) else 0.0),
            total_pnl_usd=("pnl_usd", "sum"),
        )
        .reset_index()
    )
    # Ensure both regimes appear even if empty
    for r in ("low_vol", "high_vol"):
        if r not in grouped["regime"].values:
            grouped = pd.concat(
                [grouped, pd.DataFrame([{"regime": r, "n_trades": 0, "win_rate": 0.0, "total_pnl_usd": 0.0}])],
                ignore_index=True,
            )
    return grouped.sort_values("regime").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Bootstrap CIs on backtest metrics (issue #94)
# ---------------------------------------------------------------------------
def bootstrap_metric_cis(
    trades: pd.DataFrame,
    *,
    n_resamples: int = 1000,
    confidence: float = 0.95,
    seed: int = 7,
) -> Dict[str, Dict[str, float]]:
    """Stationary-bootstrap 95% CIs for the per-trade summary metrics.

    The reported headline numbers (Sharpe, hit rate, VaR/ES, max DD)
    are point estimates on a *single* realization of the trade list.
    With ~30 trades the sampling noise alone is enormous — a Sharpe
    of 4.4 has a 95% CI on the order of ±2 even under ideal
    iid-trade assumptions. The honest thing to publish is the CI.

    We use a basic iid trade-level resample because trades are
    already serially-dependent through the entry/exit logic — the
    user-visible thing we want to characterise is "if you'd run this
    strategy on a slightly different draw of the same regime, where
    would the Sharpe land?". Block-bootstrap on the underlying
    spread series is a future refinement.

    Returns ``{metric: {"point": float, "ci_low": float, "ci_high": float}}``.
    """
    if trades is None or (hasattr(trades, "empty") and trades.empty):
        return {}

    tdf = trades.copy() if hasattr(trades, "copy") else pd.DataFrame(trades)
    n = len(tdf)
    if n < 5:
        return {}

    pnl = tdf["pnl_usd"].astype(float).to_numpy()
    days = tdf["days_held"].astype(float).to_numpy() if "days_held" in tdf.columns else np.full(n, 1.0)

    rng = np.random.default_rng(seed)

    sharpes: list[float] = []
    hits: list[float] = []
    var95s: list[float] = []
    es95s: list[float] = []
    max_dds: list[float] = []
    totals: list[float] = []

    for _ in range(int(n_resamples)):
        idx = rng.integers(0, n, size=n)
        pnl_b = pnl[idx]
        days_b = days[idx]
        std = pnl_b.std(ddof=0)
        mean_hold = days_b.mean() or 1.0
        trades_per_year = 365.0 / max(mean_hold, 1.0)
        sharpe = float((pnl_b.mean() / std) * np.sqrt(trades_per_year)) if std > 0 else 0.0
        sharpes.append(sharpe)
        hits.append(float((pnl_b > 0).mean()))
        var95s.append(float(np.quantile(pnl_b, 0.05)))
        tail = pnl_b[pnl_b <= var95s[-1]]
        es95s.append(float(tail.mean()) if tail.size else var95s[-1])
        cum = np.cumsum(pnl_b)
        running_max = np.maximum.accumulate(cum)
        max_dds.append(float((cum - running_max).min()))
        totals.append(float(pnl_b.sum()))

    alpha = (1.0 - confidence) / 2.0

    def _ci(values: list[float], point: float) -> Dict[str, float]:
        arr = np.array(values, dtype=float)
        return {
            "point": float(point),
            "ci_low": float(np.quantile(arr, alpha)),
            "ci_high": float(np.quantile(arr, 1 - alpha)),
        }

    # Point estimates (recompute from the original trades to avoid
    # round-trip-rounding mismatches against the published headline).
    std0 = pnl.std(ddof=0)
    mean_hold0 = days.mean() or 1.0
    tpy0 = 365.0 / max(mean_hold0, 1.0)
    sharpe0 = float((pnl.mean() / std0) * np.sqrt(tpy0)) if std0 > 0 else 0.0
    hit0 = float((pnl > 0).mean())
    var0 = float(np.quantile(pnl, 0.05))
    tail0 = pnl[pnl <= var0]
    es0 = float(tail0.mean()) if tail0.size else var0
    cum0 = np.cumsum(pnl)
    running_max0 = np.maximum.accumulate(cum0)
    max_dd0 = float((cum0 - running_max0).min())
    total0 = float(pnl.sum())

    return {
        "sharpe": _ci(sharpes, sharpe0),
        "hit_rate": _ci(hits, hit0),
        "var_95": _ci(var95s, var0),
        "es_95": _ci(es95s, es0),
        "max_drawdown_usd": _ci(max_dds, max_dd0),
        "total_pnl_usd": _ci(totals, total0),
        "n_resamples": {"point": float(n_resamples), "ci_low": float(n_resamples), "ci_high": float(n_resamples)},
    }


# ---------------------------------------------------------------------------
# Walk-forward OOS — fit on past, test on future, slide forward (issue #94)
# ---------------------------------------------------------------------------
def walk_forward_oos_backtest(
    spread_df: pd.DataFrame,
    *,
    fit_window_days: int = 90,
    oos_window_days: int = 30,
    entry_z: float = 2.0,
    exit_z: float = 0.2,
    slippage_per_bbl: float = 0.0,
    commission_per_trade: float = 0.0,
) -> pd.DataFrame:
    """Time-aware out-of-sample walk-forward.

    For each cursor date ``t``:
      1. Fit window = ``[t - fit_window_days, t]`` — used ONLY to
         confirm the rolling Z series has fully warmed up.
      2. Test window = ``(t, t + oos_window_days]`` — backtest runs
         on this slice using the (lagged) Z stats already in
         ``spread_df``. PnL collected from this slice is OOS by
         construction.
      3. Cursor advances by ``oos_window_days`` so test windows
         never overlap.

    The per-window stats are aggregated into a DataFrame that the
    audit document references as the "honest" Sharpe estimate vs the
    headline in-sample number.
    """
    if spread_df is None or spread_df.empty or "Z_Score" not in spread_df.columns:
        return pd.DataFrame(
            columns=["fit_start", "fit_end", "oos_start", "oos_end", "n_trades", "win_rate", "sharpe", "total_pnl_usd"]
        )

    df = spread_df.dropna(subset=["Z_Score"]).copy()
    if df.empty:
        return pd.DataFrame()

    start = df.index.min()
    end = df.index.max()
    fit_offset = pd.Timedelta(days=fit_window_days)
    oos_offset = pd.Timedelta(days=oos_window_days)

    rows: list[dict] = []
    cursor = start + fit_offset
    while cursor + oos_offset <= end:
        fit_start = cursor - fit_offset
        fit_end = cursor
        oos_start = cursor
        oos_end = cursor + oos_offset
        oos_slice = df.loc[oos_start:oos_end]
        if oos_slice.empty:
            cursor = cursor + oos_offset
            continue
        out = backtest_zscore_meanreversion(
            oos_slice,
            entry_z=entry_z,
            exit_z=exit_z,
            slippage_per_bbl=slippage_per_bbl,
            commission_per_trade=commission_per_trade,
        )
        rows.append(
            {
                "fit_start": fit_start,
                "fit_end": fit_end,
                "oos_start": oos_start,
                "oos_end": oos_end,
                "n_trades": int(out["n_trades"]),
                "win_rate": float(out["win_rate"]),
                "sharpe": float(out.get("sharpe", 0.0)),
                "total_pnl_usd": float(out["total_pnl_usd"]),
            }
        )
        cursor = cursor + oos_offset
    return pd.DataFrame(rows)


__all__ = [
    "compute_spread_zscore",
    "forecast_depletion",
    "categorize_flag_states",
    "backtest_zscore_meanreversion",
    "walk_forward_backtest",
    "walk_forward_oos_backtest",
    "monte_carlo_entry_noise",
    "regime_breakdown",
    "bootstrap_metric_cis",
]
