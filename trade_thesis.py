"""Structured Trade Thesis generator (Azure OpenAI + JSON schema).

Input: a rich :class:`ThesisContext` bundling real market state
(spread + z, mean-reversion stats, inventory regime, fleet, vol, calendar,
session). Output: a validated :class:`Thesis` dataclass.

Key features:
  * ``response_format={"type":"json_schema", ...}`` — the model is forced
    to return well-typed JSON. We validate each field and retry once with
    a pointed nudge on malformed output.
  * Guardrails clamp (a) conviction when backtest hit-rate is weak,
    (b) sizing at 20% of capital, (c) stance to "flat" when inventory
    data is missing.
  * Every call is appended to ``data/trade_theses.jsonl`` (gitignored,
    operational data).
  * If ``AZURE_OPENAI_*`` env vars are missing, we return a
    rule-based ``Thesis`` so the UI never blanks — clearly flagged via
    ``data_caveats``.

Reference: docs/ai_trade_thesis.md
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import pathlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structured context payload
# ---------------------------------------------------------------------------
@dataclass
class ThesisContext:
    # Spread state
    latest_brent: float
    latest_wti: float
    latest_spread: float
    rolling_mean_90d: float
    rolling_std_90d: float
    current_z: float
    z_percentile_5y: float           # 0..100
    days_since_last_abs_z_over_2: int

    # Mean-reversion backtest stats
    bt_hit_rate: float               # 0..1
    bt_avg_hold_days: float
    bt_avg_pnl_per_bbl: float
    bt_max_drawdown_usd: float
    bt_sharpe: float

    # Inventory regime
    inventory_source: str            # "EIA" or "FRED" or "unavailable"
    inventory_current_bbls: float
    inventory_4w_slope_bbls_per_day: float
    inventory_52w_slope_bbls_per_day: float
    inventory_floor_bbls: float
    inventory_projected_floor_date: Optional[str]   # YYYY-MM-DD
    days_of_supply: Optional[float]

    # Fleet composition
    fleet_total_mbbl: float
    fleet_jones_mbbl: float
    fleet_shadow_mbbl: float
    fleet_sanctioned_mbbl: float
    fleet_source: str                # "aisstream.io (live)" or "Historical snapshot"
    fleet_delta_vs_30d_mbbl: Optional[float]

    # Volatility regime (30-day realized)
    vol_brent_30d_pct: float
    vol_wti_30d_pct: float
    vol_spread_30d_pct: float
    vol_spread_1y_percentile: float  # 0..100

    # Calendar / session
    next_eia_release_date: Optional[str]
    session_is_open: bool
    weekend_or_holiday: bool

    # User threshold (sidebar slider)
    user_z_threshold: float

    def to_dict(self) -> dict:
        return asdict(self)

    def fingerprint(self) -> str:
        """Stable hash used as a cache key (params only, not timestamp)."""
        payload = json.dumps(
            {k: v for k, v in self.to_dict().items() if k not in ("days_since_last_abs_z_over_2",)},
            sort_keys=True, default=str,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# JSON schema exposed to the model
# ---------------------------------------------------------------------------
THESIS_JSON_SCHEMA = {
    "name": "trade_thesis",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "stance": {"type": "string", "enum": ["long_spread", "short_spread", "flat"]},
            "conviction_0_to_10": {"type": "number", "minimum": 0, "maximum": 10},
            "time_horizon_days": {"type": "integer", "minimum": 0, "maximum": 365},
            "entry": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "trigger_condition": {"type": "string"},
                    "suggested_z_level": {"type": "number"},
                    "suggested_spread_usd": {"type": "number"},
                },
                "required": ["trigger_condition", "suggested_z_level", "suggested_spread_usd"],
            },
            "exit": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "target_condition": {"type": "string"},
                    "target_z_level": {"type": "number"},
                    "stop_loss_condition": {"type": "string"},
                    "stop_z_level": {"type": "number"},
                },
                "required": ["target_condition", "target_z_level", "stop_loss_condition", "stop_z_level"],
            },
            "position_sizing": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "method": {"type": "string", "enum": ["fixed_fractional", "volatility_scaled", "kelly"]},
                    "suggested_pct_of_capital": {"type": "number", "minimum": 0, "maximum": 100},
                    "rationale": {"type": "string"},
                },
                "required": ["method", "suggested_pct_of_capital", "rationale"],
            },
            "thesis_summary": {"type": "string"},
            "key_drivers": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 6},
            "invalidation_risks": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 6},
            "catalyst_watchlist": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "event": {"type": "string"},
                        "date": {"type": "string"},
                        "expected_impact": {"type": "string"},
                    },
                    "required": ["event", "date", "expected_impact"],
                },
            },
            "data_caveats": {"type": "array", "items": {"type": "string"}},
            "disclaimer_shown": {"type": "boolean"},
        },
        "required": [
            "stance", "conviction_0_to_10", "time_horizon_days",
            "entry", "exit", "position_sizing",
            "thesis_summary", "key_drivers", "invalidation_risks",
            "catalyst_watchlist", "data_caveats", "disclaimer_shown",
        ],
    },
    "strict": True,
}


SYSTEM_PROMPT = (
    "You are a senior commodities trading analyst specialising in the Brent-WTI "
    "spread and physical crude flows. You produce rigorous trade theses grounded "
    "ONLY in the structured data provided. You do not speculate beyond what the "
    "data supports. You state confidence honestly. You always flag risks that "
    "would invalidate the thesis. Output must be valid JSON matching the provided schema.\n\n"
    "Your output JSON uses technical field names, but a translation layer renders "
    "them in plain language for traders without quant backgrounds. Prefer terms "
    "like \"dislocation\" over \"Z-score\" and \"snap-back to normal\" over "
    "\"mean reversion\" in your thesis_summary and key_drivers prose. Still be "
    "precise — say \"dislocation of 2.4\" not \"the spread is weird.\""
)


# ---------------------------------------------------------------------------
# Output shape
# ---------------------------------------------------------------------------
@dataclass
class Thesis:
    raw: dict
    generated_at: str
    source: str                          # "Azure OpenAI: <deployment>" or "rule-based (fallback)"
    model: Optional[str] = None
    context_fingerprint: str = ""
    guardrails_applied: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------
def _apply_guardrails(raw: dict, ctx: ThesisContext) -> tuple[dict, list[str]]:
    notes: list[str] = []

    # 1) If inventory data missing → force flat + caveat
    if ctx.inventory_source in ("unavailable", "", "missing"):
        if raw.get("stance") != "flat":
            notes.append("forced stance=flat (inventory feed unavailable)")
            raw["stance"] = "flat"
            raw["conviction_0_to_10"] = min(raw.get("conviction_0_to_10", 0), 3)
        raw.setdefault("data_caveats", []).append("Inventory feed unavailable — stance forced flat.")

    # 2) High conviction on weak backtest → downgrade
    try:
        conv = float(raw.get("conviction_0_to_10", 0))
    except Exception:
        conv = 0.0
    if conv > 7 and ctx.bt_hit_rate < 0.55:
        notes.append(
            f"calibration adjustment: conviction {conv:.1f} → 5.0 "
            f"(backtest hit rate {ctx.bt_hit_rate*100:.0f}% < 55%)"
        )
        raw["conviction_0_to_10"] = 5.0
        raw.setdefault("data_caveats", []).append(
            f"Model conviction capped at 5/10 because historical hit rate on |Z|>threshold "
            f"entries is {ctx.bt_hit_rate*100:.0f}%."
        )

    # 3) Sizing cap at 20%
    sizing = raw.get("position_sizing") or {}
    pct = float(sizing.get("suggested_pct_of_capital", 0) or 0)
    if pct > 20.0:
        notes.append(f"sizing cap applied: {pct:.1f}% → 20.0%")
        sizing["suggested_pct_of_capital"] = 20.0
        raw["position_sizing"] = sizing
        raw.setdefault("data_caveats", []).append(
            "Suggested position size capped at 20% of capital by policy."
        )

    # 4) Force disclaimer on
    raw["disclaimer_shown"] = True

    return raw, notes


# ---------------------------------------------------------------------------
# Rule-based fallback (used when Azure OpenAI isn't configured)
# ---------------------------------------------------------------------------
def _rule_based_fallback(ctx: ThesisContext) -> dict:
    z = ctx.current_z
    thr = max(1.0, ctx.user_z_threshold)
    if ctx.inventory_source in ("unavailable", ""):
        stance = "flat"
    elif z >= thr:
        stance = "short_spread"
    elif z <= -thr:
        stance = "long_spread"
    else:
        stance = "flat"

    conviction = min(10.0, max(0.0, abs(z) / thr * 6.0))
    target_z = 0.0
    stop_z = z + (2.0 if z > 0 else -2.0)

    return {
        "stance": stance,
        "conviction_0_to_10": float(round(conviction, 1)),
        "time_horizon_days": int(max(5, min(60, ctx.bt_avg_hold_days or 30))),
        "entry": {
            "trigger_condition": f"Spread Z remains {'>= ' + str(thr) if z > 0 else '<= -' + str(thr)} σ at session open",
            "suggested_z_level": float(round(z, 2)),
            "suggested_spread_usd": float(round(ctx.latest_spread, 2)),
        },
        "exit": {
            "target_condition": "Z reverts through 0",
            "target_z_level": float(target_z),
            "stop_loss_condition": "Z extends 2σ beyond entry",
            "stop_z_level": float(round(stop_z, 2)),
        },
        "position_sizing": {
            "method": "fixed_fractional",
            "suggested_pct_of_capital": float(round(min(10.0, conviction), 1)),
            "rationale": "Proportional to |Z| over the user threshold; capped at 10%.",
        },
        "thesis_summary": (
            f"Brent {ctx.latest_brent:.2f} / WTI {ctx.latest_wti:.2f}; spread {ctx.latest_spread:+.2f} "
            f"at Z {z:+.2f}σ ({ctx.z_percentile_5y:.0f}th pct 5y). "
            f"Mean-reversion backtest hit rate {ctx.bt_hit_rate*100:.0f}% with {ctx.bt_avg_hold_days:.0f}-day avg hold. "
            "Rule-based fallback — Azure OpenAI not configured."
        ),
        "key_drivers": [
            f"Spread Z {z:+.2f}σ vs user threshold ±{thr:.1f}σ",
            f"Inventory source: {ctx.inventory_source} (current {ctx.inventory_current_bbls/1e6:,.0f} Mbbl)",
            f"Backtest Sharpe {ctx.bt_sharpe:.2f}, max DD ${ctx.bt_max_drawdown_usd:,.0f}",
        ],
        "invalidation_risks": [
            "Structural break in the WTI-Brent arb (pipeline or export policy change)",
            "Major geopolitical shock that moves one leg independently",
            "Sustained low liquidity at entry (crossing wide bid-ask)",
        ],
        "catalyst_watchlist": [
            {"event": "EIA weekly release", "date": ctx.next_eia_release_date or "Wednesday",
             "expected_impact": "Can flip the spread 0.5σ in either direction."},
        ],
        "data_caveats": [
            "Generated via rule-based fallback (Azure OpenAI unreachable or unconfigured).",
        ],
        "disclaimer_shown": True,
    }


# ---------------------------------------------------------------------------
# LLM call
# ---------------------------------------------------------------------------
def _call_azure_openai(ctx: ThesisContext) -> tuple[dict, str]:
    """Return (raw_dict, model_label). Raises on failure."""
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    api_key = os.environ.get("AZURE_OPENAI_KEY")
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")
    deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")

    if not (endpoint and api_key):
        raise RuntimeError("AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_KEY not set")

    from openai import AzureOpenAI  # type: ignore

    client = AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
    )

    def _once(retry_nudge: str = "") -> dict:
        user_payload = {
            "note": "All fields are real current values. Produce a trade thesis that cites them explicitly.",
            "context": ctx.to_dict(),
        }
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload, default=str)},
        ]
        if retry_nudge:
            messages.append({"role": "user", "content": retry_nudge})

        resp = client.chat.completions.create(
            model=deployment,
            messages=messages,
            response_format={"type": "json_schema", "json_schema": THESIS_JSON_SCHEMA},
            temperature=0.2,
            max_completion_tokens=1200,
        )
        content = resp.choices[0].message.content or "{}"
        parsed = json.loads(content)
        return parsed

    try:
        return _once(), f"Azure OpenAI: {deployment}"
    except json.JSONDecodeError as exc:
        logger.warning("Malformed JSON from model, retrying once: %r", exc)
        nudge = (
            "Your previous output was not valid JSON. Produce ONLY a JSON object "
            "matching the schema you were given. No code fences, no commentary."
        )
        return _once(retry_nudge=nudge), f"Azure OpenAI (retry): {deployment}"


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
_AUDIT_PATH = pathlib.Path("data/trade_theses.jsonl")


def _append_audit(ctx: ThesisContext, thesis: Thesis) -> None:
    try:
        _AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": thesis.generated_at,
            "source": thesis.source,
            "model": thesis.model,
            "context_fingerprint": thesis.context_fingerprint,
            "context": ctx.to_dict(),
            "thesis": thesis.raw,
            "guardrails": thesis.guardrails_applied,
        }
        with _AUDIT_PATH.open("a") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except Exception as exc:
        logger.debug("audit write failed: %r", exc)


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
def generate_thesis(ctx: ThesisContext, *, log: bool = True) -> Thesis:
    """Return a validated :class:`Thesis`. Never raises."""
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fingerprint = ctx.fingerprint()
    model_label = "rule-based (fallback)"
    raw: dict = {}

    try:
        raw, model_label = _call_azure_openai(ctx)
    except Exception as exc:
        logger.info("Azure OpenAI unavailable, rule-based fallback: %r", exc)
        raw = _rule_based_fallback(ctx)
        raw.setdefault("data_caveats", []).append(f"Azure OpenAI fallback reason: {exc!r}")

    raw, notes = _apply_guardrails(raw, ctx)

    thesis = Thesis(
        raw=raw,
        generated_at=generated_at,
        source=model_label,
        model=os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini") if "Azure" in model_label else None,
        context_fingerprint=fingerprint,
        guardrails_applied=notes,
    )
    if log:
        _append_audit(ctx, thesis)
    return thesis


__all__ = [
    "ThesisContext",
    "Thesis",
    "generate_thesis",
    "THESIS_JSON_SCHEMA",
    "SYSTEM_PROMPT",
]
