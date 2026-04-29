"""Assemble a :class:`ThesisContext` from the dashboard's current state."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import numpy as np
import pandas as pd

from trade_thesis import ThesisContext


def _percentile_rank(series: pd.Series, value: float) -> float:
    s = series.dropna()
    if s.empty:
        return 50.0
    return float((s <= value).mean() * 100.0)


def _days_since_last_abs_z_over(series: pd.Series, threshold: float = 2.0) -> int:
    s = series.dropna()
    if s.empty:
        return -1
    mask = s.abs() >= threshold
    if not mask.any():
        return len(s)
    last_idx = s.index[mask][-1]
    now = s.index[-1]
    return int((now - last_idx).days)


def _linear_slope_per_day(series: pd.Series) -> float:
    s = series.dropna()
    if len(s) < 2:
        return 0.0
    x = np.array([(d - s.index[0]).days for d in s.index], dtype=float)
    y = s.values.astype(float)
    slope, _ = np.polyfit(x, y, 1)
    return float(slope)


def _realized_vol_pct(prices: pd.Series, window: int = 30) -> float:
    s = prices.dropna()
    if len(s) < window + 2:
        return 0.0
    rets = np.log(s / s.shift(1)).dropna().tail(window)
    if rets.empty:
        return 0.0
    return float(rets.std(ddof=0) * np.sqrt(252) * 100.0)


def _realized_vol_series_pct(prices: pd.Series, window: int = 30) -> pd.Series:
    s = prices.dropna()
    rets = np.log(s / s.shift(1)).dropna()
    return rets.rolling(window).std(ddof=0) * np.sqrt(252) * 100.0


def _next_wednesday(today: pd.Timestamp) -> pd.Timestamp:
    # EIA weekly petroleum status report is released Wednesdays at 10:30 ET.
    days_ahead = (2 - today.weekday()) % 7   # Monday=0, Wednesday=2
    if days_ahead == 0:
        days_ahead = 7
    return today + pd.Timedelta(days=days_ahead)


def _hours_to_next_eia_release(now: Optional[datetime]) -> Optional[float]:
    """Hours until the next EIA weekly petroleum status release.

    EIA publishes the weekly report on Wednesdays at 14:30 UTC
    (10:30 ET, standard time — DST differences are not accounted for
    in this minimal helper; if you need DST precision, compose with a
    calendar API).

    Returns None when `now` is None so a missing timestamp does not
    propagate as a spurious zero.
    """
    if now is None:
        return None
    days_ahead = (2 - now.weekday()) % 7
    candidate = now.replace(hour=14, minute=30, second=0, microsecond=0) + timedelta(days=days_ahead)
    if candidate <= now:
        candidate += timedelta(days=7)
    return (candidate - now).total_seconds() / 3600.0


def build_context(
    *,
    pricing_res,
    inventory_res,
    spread_df: pd.DataFrame,
    backtest: dict,
    depletion: dict,
    ais_agg: pd.DataFrame,
    ais_with_cat: pd.DataFrame,
    z_threshold: float,
    floor_bbls: float,
    coint_info: dict | None = None,
    crack_info: dict | None = None,
    cftc_res=None,
    regime_info: dict | None = None,
    garch_info: dict | None = None,
    hormuz_info: dict | None = None,
    iran_production_info: dict | None = None,
    iran_tanker_info: dict | None = None,
    news_info: dict | None = None,
    ofac_info: dict | None = None,
    russia_info: dict | None = None,
) -> ThesisContext:
    latest_brent = float(pricing_res.frame["Brent"].iloc[-1])
    latest_wti = float(pricing_res.frame["WTI"].iloc[-1])
    latest_spread = latest_brent - latest_wti

    z_series = spread_df["Z_Score"].dropna() if "Z_Score" in spread_df.columns else pd.Series(dtype=float)
    current_z = float(z_series.iloc[-1]) if not z_series.empty else 0.0
    rolling_mean_90d = float(spread_df["Spread_Mean"].iloc[-1]) if "Spread_Mean" in spread_df and spread_df["Spread_Mean"].notna().any() else 0.0
    rolling_std_90d = float(spread_df["Spread_Std"].iloc[-1]) if "Spread_Std" in spread_df and spread_df["Spread_Std"].notna().any() else 0.0
    z_percentile = _percentile_rank(z_series, current_z) if not z_series.empty else 50.0
    days_since = _days_since_last_abs_z_over(z_series, 2.0)

    inventory_source = "unavailable"
    inv_current = float("nan")
    slope_4w = 0.0
    slope_52w = 0.0
    proj_date = None
    days_of_supply: float | None = None

    if inventory_res is not None and getattr(inventory_res, "frame", None) is not None and not inventory_res.frame.empty:
        inventory_source = inventory_res.source
        inv = inventory_res.frame["Total_Inventory_bbls"].dropna()
        if not inv.empty:
            inv_current = float(inv.iloc[-1])
            slope_4w = _linear_slope_per_day(inv.tail(4))
            slope_52w = _linear_slope_per_day(inv.tail(52))
            # US crude demand ~20 Mbbl/d — rough days-of-supply at 4w slope pace
            if slope_4w < 0:
                # If drawing down at |slope| bbls/day, days until floor breach
                floor_gap = inv_current - floor_bbls
                if floor_gap > 0:
                    days_of_supply = float(floor_gap / abs(slope_4w))
        proj_date = depletion.get("projected_floor_date")
        if proj_date is not None and hasattr(proj_date, "strftime"):
            proj_date = proj_date.strftime("%Y-%m-%d")

    # Fleet
    jones = float(ais_agg.loc[ais_agg["Category"] == "Jones Act / Domestic", "Total_Cargo_Mbbl"].sum()) if "Category" in ais_agg else 0.0
    shadow = float(ais_agg.loc[ais_agg["Category"] == "Shadow Risk", "Total_Cargo_Mbbl"].sum()) if "Category" in ais_agg else 0.0
    sanctioned = float(ais_agg.loc[ais_agg["Category"] == "Sanctioned", "Total_Cargo_Mbbl"].sum()) if "Category" in ais_agg else 0.0
    total_fleet = float(ais_with_cat["Cargo_Volume_bbls"].sum() / 1e6) if "Cargo_Volume_bbls" in ais_with_cat else (jones + shadow + sanctioned)

    # Volatility
    vol_brent = _realized_vol_pct(pricing_res.frame["Brent"], 30)
    vol_wti = _realized_vol_pct(pricing_res.frame["WTI"], 30)
    spread_series = pricing_res.frame["Brent"] - pricing_res.frame["WTI"]
    vol_spread = _realized_vol_pct(spread_series, 30)
    vol_spread_series = _realized_vol_series_pct(spread_series, 30).tail(252).dropna()
    vol_percentile = _percentile_rank(vol_spread_series, vol_spread) if not vol_spread_series.empty else 50.0

    # Cointegration + crack — merge optional dicts into local vars
    coint_info = coint_info or {}
    crack_info = crack_info or {}
    cushing_series = None
    try:
        cushing_series = inventory_res.frame.get("Cushing_bbls") if inventory_res is not None else None
    except Exception:
        cushing_series = None
    cushing_current = float(cushing_series.dropna().iloc[-1]) if cushing_series is not None and cushing_series.notna().any() else None
    cushing_4w_slope = None
    if cushing_series is not None and cushing_series.notna().sum() > 3:
        cu = cushing_series.dropna().tail(4)
        if len(cu) >= 2:
            days = max(1, (cu.index[-1] - cu.index[0]).days)
            cushing_4w_slope = float((cu.iloc[-1] - cu.iloc[0]) / days)

    # CFTC positioning (Managed Money Z-score + percentile — latest report)
    cftc_as_of = None
    cftc_oi = None
    cftc_mm = None
    cftc_pm = None
    cftc_sw = None
    cftc_mm_z = None
    cftc_mm_pct = None
    if cftc_res is not None and getattr(cftc_res, "frame", None) is not None and not cftc_res.frame.empty:
        latest = cftc_res.frame.iloc[-1]
        cftc_as_of = cftc_res.frame.index[-1].strftime("%Y-%m-%d")
        cftc_oi = int(latest.get("open_interest", 0) or 0)
        if "mm_net" in cftc_res.frame.columns:
            cftc_mm = int(latest["mm_net"])
            cftc_mm_z = float(cftc_res.mm_zscore_3y) if cftc_res.mm_zscore_3y is not None else None
            series = cftc_res.frame["mm_net"].dropna().tail(156)
            if not series.empty:
                cftc_mm_pct = _percentile_rank(series, float(latest["mm_net"]))
        if "producer_net" in cftc_res.frame.columns:
            cftc_pm = int(latest["producer_net"])
        if "swap_net" in cftc_res.frame.columns:
            cftc_sw = int(latest["swap_net"])

    # Calendar
    today = pd.Timestamp.now(tz="UTC").tz_convert(None).normalize()
    eia_next = _next_wednesday(today).strftime("%Y-%m-%d")

    # NYMEX crude session: roughly 6pm ET Sunday through 5pm ET Friday. We approximate.
    now_utc = datetime.now(timezone.utc)
    dow = now_utc.weekday()   # 0=Mon, 5=Sat, 6=Sun
    hour = now_utc.hour       # UTC
    weekend = dow in (5,) or (dow == 6 and hour < 23) or (dow == 4 and hour >= 21)
    session_open = not weekend

    return ThesisContext(
        latest_brent=latest_brent,
        latest_wti=latest_wti,
        latest_spread=latest_spread,
        rolling_mean_90d=rolling_mean_90d,
        rolling_std_90d=rolling_std_90d,
        current_z=current_z,
        z_percentile_5y=z_percentile,
        days_since_last_abs_z_over_2=int(days_since if days_since is not None and days_since >= 0 else -1),
        bt_hit_rate=float(backtest.get("win_rate", 0.0)),
        bt_avg_hold_days=float(backtest.get("avg_days_held", 0.0)),
        bt_avg_pnl_per_bbl=float(backtest.get("avg_pnl_per_bbl", 0.0)),
        bt_max_drawdown_usd=float(backtest.get("max_drawdown_usd", 0.0)),
        bt_sharpe=float(backtest.get("sharpe", 0.0)),
        inventory_source=str(inventory_source),
        inventory_current_bbls=float(inv_current) if inv_current == inv_current else 0.0,
        inventory_4w_slope_bbls_per_day=float(slope_4w),
        inventory_52w_slope_bbls_per_day=float(slope_52w),
        inventory_floor_bbls=float(floor_bbls),
        inventory_projected_floor_date=proj_date if isinstance(proj_date, str) else None,
        days_of_supply=days_of_supply,
        fleet_total_mbbl=float(total_fleet),
        fleet_jones_mbbl=float(jones),
        fleet_shadow_mbbl=float(shadow),
        fleet_sanctioned_mbbl=float(sanctioned),
        fleet_source="",  # filled by caller
        fleet_delta_vs_30d_mbbl=None,
        vol_brent_30d_pct=float(vol_brent),
        vol_wti_30d_pct=float(vol_wti),
        vol_spread_30d_pct=float(vol_spread),
        vol_spread_1y_percentile=float(vol_percentile),
        next_eia_release_date=eia_next,
        session_is_open=bool(session_open),
        weekend_or_holiday=bool(weekend),
        user_z_threshold=float(z_threshold),
        coint_p_value=float(coint_info.get("p_value", float("nan"))) if coint_info else float("nan"),
        coint_verdict=str(coint_info.get("verdict", "inconclusive")) if coint_info else "inconclusive",
        coint_hedge_ratio=float(coint_info.get("hedge_ratio", float("nan"))) if coint_info else float("nan"),
        coint_half_life_days=(float(coint_info.get("half_life_days"))
                              if coint_info and coint_info.get("half_life_days") is not None
                              else None),
        cushing_current_bbls=cushing_current,
        cushing_4w_slope_bbls_per_day=cushing_4w_slope,
        crack_321_usd=(float(crack_info.get("latest_crack_usd"))
                       if crack_info and crack_info.get("latest_crack_usd") == crack_info.get("latest_crack_usd")
                       else None),
        crack_corr_30d=(float(crack_info.get("corr_30d_vs_brent_wti"))
                        if crack_info and crack_info.get("corr_30d_vs_brent_wti") == crack_info.get("corr_30d_vs_brent_wti")
                        else None),
        cftc_as_of_date=cftc_as_of,
        cftc_open_interest=cftc_oi,
        cftc_mm_net=cftc_mm,
        cftc_producer_net=cftc_pm,
        cftc_swap_net=cftc_sw,
        cftc_mm_zscore_3y=cftc_mm_z,
        cftc_mm_pctile_3y=cftc_mm_pct,
        # --- Q3 prediction-quality slice ---------------------------------
        # Regime + GARCH come in as plain dicts so build_context stays
        # unaware of the backend.services.* layer (which is where the
        # services live). Each field defaults to None so legacy callers
        # that don't pass these blocks get the unchanged context shape.
        regime_term_structure=(str(regime_info.get("term_structure"))
                               if regime_info and regime_info.get("term_structure") is not None
                               else None),
        regime_vol_bucket=(str(regime_info.get("vol_bucket"))
                           if regime_info and regime_info.get("vol_bucket") is not None
                           else None),
        regime_vol_percentile=(float(regime_info.get("vol_percentile"))
                               if regime_info and regime_info.get("vol_percentile") is not None
                               else None),
        regime_realized_vol_20d_pct=(float(regime_info.get("realized_vol_20d_pct"))
                                     if regime_info and regime_info.get("realized_vol_20d_pct") is not None
                                     else None),
        garch_z=(float(garch_info.get("z"))
                 if garch_info and garch_info.get("z") is not None
                 else None),
        garch_ok=(bool(garch_info.get("ok"))
                  if garch_info and garch_info.get("ok") is not None
                  else None),
        garch_sigma=(float(garch_info.get("sigma"))
                     if garch_info and garch_info.get("sigma") is not None
                     else None),
        garch_persistence=(float(garch_info.get("persistence"))
                           if garch_info and garch_info.get("persistence") is not None
                           else None),
        garch_fallback_reason=(str(garch_info.get("fallback_reason"))
                               if garch_info and garch_info.get("fallback_reason")
                               else None),
        # --- Geopolitical: Strait of Hormuz ---------------------------
        # Same plumbing pattern as the Q3 slice above — accepts an
        # optional `hormuz_info` dict. Caller passes `{"transits_24h":
        # int, "transits_pct_1y": float}` from
        # `geopolitical_service.compute_envelope`. Both fields stay
        # None when the dict is absent / partial so existing callers
        # keep working.
        hormuz_transits_24h=(int(hormuz_info.get("transits_24h"))
                             if hormuz_info and hormuz_info.get("transits_24h") is not None
                             else None),
        hormuz_transits_pct_1y=(float(hormuz_info.get("transits_pct_1y"))
                                if hormuz_info and hormuz_info.get("transits_pct_1y") is not None
                                else None),
        # --- Iran crude production (issue #79) ---------------------------
        iran_production_kbpd=(float(iran_production_info.get("latest_kbpd"))
                              if iran_production_info
                              and iran_production_info.get("latest_kbpd") is not None
                              else None),
        # --- Iran tanker flow (issue #78) -------------------------------
        iran_export_tankers_7d=(int(iran_tanker_info.get("exports_7d"))
                                if iran_tanker_info
                                and iran_tanker_info.get("exports_7d") is not None
                                else None),
        iran_import_tankers_7d=(int(iran_tanker_info.get("imports_7d"))
                                if iran_tanker_info
                                and iran_tanker_info.get("imports_7d") is not None
                                else None),
        # --- News headlines + sentiment (issue #80) ---------------------
        recent_headlines=(
            list(news_info.get("top_headlines", []))
            if news_info and news_info.get("top_headlines")
            else []
        ),
        # --- OFAC sanctions delta (issue #81) ---------------------------
        new_sanctions_iran_30d=(int(ofac_info.get("delta_iran"))
                                if ofac_info and ofac_info.get("delta_iran") is not None
                                else None),
        new_sanctions_russia_30d=(int(ofac_info.get("delta_russia"))
                                  if ofac_info and ofac_info.get("delta_russia") is not None
                                  else None),
        new_sanctions_venezuela_30d=(int(ofac_info.get("delta_venezuela"))
                                     if ofac_info and ofac_info.get("delta_venezuela") is not None
                                     else None),
        # --- Russia mirror (issue #82) ---------------------------------
        russia_chokepoint_transits_24h=(int(russia_info.get("chokepoint_transits_24h"))
                                        if russia_info and russia_info.get("chokepoint_transits_24h") is not None
                                        else None),
        russia_chokepoint_transits_pct_1y=(float(russia_info.get("percentile_1y"))
                                           if russia_info and russia_info.get("percentile_1y") is not None
                                           else None),
        russia_export_tankers_7d=(int(russia_info.get("exports_7d"))
                                  if russia_info and russia_info.get("exports_7d") is not None
                                  else None),
        russia_import_tankers_7d=(int(russia_info.get("imports_7d"))
                                  if russia_info and russia_info.get("imports_7d") is not None
                                  else None),
    )
