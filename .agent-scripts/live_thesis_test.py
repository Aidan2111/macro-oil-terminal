"""Live Azure OpenAI trade thesis smoke test.

Assembles a realistic ThesisContext from real EIA + synthetic backtest
stats, calls the real gpt-4o-mini deployment, prints the validated
JSON, asserts all required schema keys are present.
"""

from __future__ import annotations

import json
import os
import sys

from trade_thesis import ThesisContext, THESIS_JSON_SCHEMA, generate_thesis


ENDPOINT = os.environ.get("AZURE_OPENAI_ENDPOINT")
KEY = os.environ.get("AZURE_OPENAI_KEY")
if not (ENDPOINT and KEY):
    print("Need AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_KEY in env", file=sys.stderr)
    sys.exit(2)


ctx = ThesisContext(
    latest_brent=92.41, latest_wti=88.65, latest_spread=3.76,
    rolling_mean_90d=3.40, rolling_std_90d=0.62,
    current_z=0.58, z_percentile_5y=68.0, days_since_last_abs_z_over_2=112,
    bt_hit_rate=0.64, bt_avg_hold_days=31.0, bt_avg_pnl_per_bbl=1.18,
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

th = generate_thesis(ctx, log=False)
print("=== Source:", th.source)
print("=== Model:", th.model)
print("=== Fingerprint:", th.context_fingerprint)
print("=== Guardrails applied:", th.guardrails_applied)
print("=== Raw thesis ===")
print(json.dumps(th.raw, indent=2))

required = set(THESIS_JSON_SCHEMA["schema"]["required"])
missing = required - set(th.raw.keys())
assert not missing, f"missing keys: {missing}"
assert th.raw["disclaimer_shown"] is True
assert th.raw["stance"] in ("long_spread", "short_spread", "flat")
assert isinstance(th.raw["entry"], dict)
print("\nLIVE SCHEMA VALID ✔")
