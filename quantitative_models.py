"""Quantitative logic for the oil-terminal dashboard.

Three public helpers:
  * compute_spread_zscore   – daily Brent-WTI spread + rolling 90d Z
  * forecast_depletion      – LinearRegression on trailing N weeks
  * categorize_flag_states  – aggregate cargo by policy category
"""

from __future__ import annotations

from datetime import timedelta
from typing import Dict, Tuple

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
    """
    if prices is None or prices.empty:
        return pd.DataFrame(
            columns=["Brent", "WTI", "Spread", "Spread_Mean", "Spread_Std", "Z_Score"]
        )

    df = prices.copy()
    if "Brent" not in df.columns or "WTI" not in df.columns:
        raise ValueError("prices must contain 'Brent' and 'WTI' columns")

    df["Spread"] = df["Brent"] - df["WTI"]
    df["Spread_Mean"] = df["Spread"].rolling(window=window, min_periods=max(5, window // 3)).mean()
    df["Spread_Std"] = df["Spread"].rolling(window=window, min_periods=max(5, window // 3)).std()
    # Guard against divide-by-zero
    std_safe = df["Spread_Std"].replace(0, np.nan)
    df["Z_Score"] = (df["Spread"] - df["Spread_Mean"]) / std_safe
    df["Z_Score"] = df["Z_Score"].replace([np.inf, -np.inf], np.nan)
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
                pnl_per_bbl = (s - entry_spread) * position
                trades.append(
                    {
                        "entry_date": entry_date,
                        "exit_date": date,
                        "side": side,
                        "entry_spread": entry_spread,
                        "exit_spread": s,
                        "pnl_per_bbl": pnl_per_bbl,
                        "pnl_usd": pnl_per_bbl * notional_bbls,
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

        out.update(
            {
                "trades": tdf.sort_values("entry_date").reset_index(drop=True),
                "total_pnl_usd": total,
                "n_trades": int(len(tdf)),
                "win_rate": wins / len(tdf),
                "avg_days_held": float(tdf["days_held"].mean()),
                "avg_pnl_per_bbl": float(tdf["pnl_per_bbl"].mean()),
                "equity_curve": equity.reset_index(drop=True),
            }
        )

    return out


__all__ = [
    "compute_spread_zscore",
    "forecast_depletion",
    "categorize_flag_states",
    "backtest_zscore_meanreversion",
]
