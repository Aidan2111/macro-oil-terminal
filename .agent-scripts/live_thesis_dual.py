"""Exercise both fast (gpt-4o) and deep (o4-mini) modes end-to-end."""

from __future__ import annotations

import json
import os
import sys
import time

from trade_thesis import ThesisContext, generate_thesis


def _ctx(z=2.1):
    return ThesisContext(
        latest_brent=92.41, latest_wti=88.65, latest_spread=3.76,
        rolling_mean_90d=3.40, rolling_std_90d=0.62,
        current_z=z, z_percentile_5y=70.0, days_since_last_abs_z_over_2=45,
        bt_hit_rate=0.66, bt_avg_hold_days=28.0, bt_avg_pnl_per_bbl=1.18,
        bt_max_drawdown_usd=-3800.0, bt_sharpe=1.42,
        inventory_source="EIA",
        inventory_current_bbls=463_804_000.0,
        inventory_4w_slope_bbls_per_day=-187_500.0,
        inventory_52w_slope_bbls_per_day=-22_000.0,
        inventory_floor_bbls=300_000_000.0,
        inventory_projected_floor_date="2028-12-14",
        days_of_supply=8700.0,
        fleet_total_mbbl=696.5, fleet_jones_mbbl=138.1,
        fleet_shadow_mbbl=329.4, fleet_sanctioned_mbbl=150.2,
        fleet_source="Historical snapshot (Q3 2024)",
        fleet_delta_vs_30d_mbbl=None,
        vol_brent_30d_pct=27.3, vol_wti_30d_pct=29.1,
        vol_spread_30d_pct=11.2, vol_spread_1y_percentile=42.0,
        next_eia_release_date="2026-04-22", session_is_open=True,
        weekend_or_holiday=False, user_z_threshold=2.0,
    )


def _run(mode: str, stream: bool):
    seen_bytes = [0]

    def _h(d: str):
        seen_bytes[0] += len(d)

    t0 = time.monotonic()
    th = generate_thesis(_ctx(), mode=mode, stream_handler=_h if stream else None, log=False)
    dt = time.monotonic() - t0
    print(f"\n=== {mode} / stream={stream} ===")
    print(f"  source: {th.source}")
    print(f"  latency: {dt:.2f}s  (internal: {th.latency_s:.2f}s)")
    print(f"  streamed: {th.streamed}  retried: {th.retried}")
    print(f"  stream bytes seen: {seen_bytes[0]}")
    print(f"  stance: {th.raw.get('stance')} · conviction: {th.raw.get('conviction_0_to_10')} · horizon: {th.raw.get('time_horizon_days')}d")
    rs = (th.raw.get("reasoning_summary") or "")[:220]
    print(f"  reasoning_summary: {rs}...")
    return th


if __name__ == "__main__":
    _run("fast", stream=True)
    _run("deep", stream=True)
    _run("fast", stream=False)
