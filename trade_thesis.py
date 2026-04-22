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
from typing import Any, Callable, Optional

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

    # --- Added after initial release (optional — default to sentinels so
    #     existing audit-log records still deserialise). All these let the
    #     LLM cite richer structure without breaking the frozen schema.
    coint_p_value: float = float("nan")
    coint_verdict: str = "inconclusive"
    coint_hedge_ratio: float = float("nan")
    coint_half_life_days: Optional[float] = None
    cushing_current_bbls: Optional[float] = None
    cushing_4w_slope_bbls_per_day: Optional[float] = None
    crack_321_usd: Optional[float] = None
    crack_corr_30d: Optional[float] = None

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
            # In deep/reasoning mode the model provides a plain-language
            # summary of its reasoning trace. Optional by design.
            "reasoning_summary": {"type": "string"},
        },
        "required": [
            "stance", "conviction_0_to_10", "time_horizon_days",
            "entry", "exit", "position_sizing",
            "thesis_summary", "key_drivers", "invalidation_risks",
            "catalyst_watchlist", "data_caveats", "disclaimer_shown",
            "reasoning_summary",
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
    "precise — say \"dislocation of 2.4\" not \"the spread is weird.\"\n\n"
    "The JSON schema has a required ``reasoning_summary`` field. In Quick-read "
    "mode keep it short (1-2 sentences describing the path from data to "
    "conclusion). In Deep-analysis mode expand it to 3-6 sentences covering "
    "the competing hypotheses you considered and why you picked the stance you did."
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
    mode: str = "fast"                   # "fast" | "deep" | "legacy" | "rule-based"
    latency_s: float = 0.0
    streamed: bool = False
    retried: bool = False

    def one_line(self) -> str:
        stance = self.raw.get("stance", "flat")
        conv = float(self.raw.get("conviction_0_to_10", 0.0))
        hz = int(self.raw.get("time_horizon_days", 0))
        return f"{stance} · {conv:.1f}/10 · {hz}d · {self.mode}"


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

    # 3b) High-vol regime → cap position sizing at 2% of capital.
    try:
        vol_pct = float(getattr(ctx, "vol_spread_1y_percentile", float("nan")))
    except Exception:
        vol_pct = float("nan")
    if vol_pct == vol_pct and vol_pct > 85.0:
        sz = raw.get("position_sizing") or {}
        cur_pct = float(sz.get("suggested_pct_of_capital", 0) or 0)
        if cur_pct > 2.0:
            notes.append(
                f"high-vol clamp: sizing {cur_pct:.1f}% → 2.0% "
                f"(spread 30d vol is at {vol_pct:.0f}th percentile of 1y)"
            )
            sz["suggested_pct_of_capital"] = 2.0
            raw["position_sizing"] = sz
            raw.setdefault("data_caveats", []).append(
                f"Spread realised-vol is in the top 15% of its 1y range "
                f"({vol_pct:.0f}th pct). Position size capped at 2% of "
                "capital by policy until vol mean-reverts."
            )

    # 4) Cointegration-broken → clamp conviction ≤ 5 and mark caveat.
    if getattr(ctx, "coint_verdict", "inconclusive") == "not_cointegrated":
        try:
            cur = float(raw.get("conviction_0_to_10", 0))
        except Exception:
            cur = 0.0
        if cur > 5.0:
            notes.append(
                f"cointegration clamp: conviction {cur:.1f} → 5.0 "
                f"(Brent-WTI fail Engle-Granger, p={getattr(ctx, 'coint_p_value', float('nan')):.3f})"
            )
            raw["conviction_0_to_10"] = 5.0
        raw.setdefault("data_caveats", []).append(
            "Brent-WTI currently fail the Engle-Granger cointegration test. "
            "Mean-reversion sizing is downgraded — the 'snap-back' model is "
            "on thin ice in this regime."
        )

    # 5) Force disclaimer on
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
        "reasoning_summary": (
            "Rule-based path: compare dislocation to the user threshold; "
            "pick a stance; size by |dislocation|/threshold. No model reasoning."
        ),
    }


# ---------------------------------------------------------------------------
# Mode → deployment resolution
# ---------------------------------------------------------------------------
_VALID_MODES = ("fast", "deep", "legacy")
_DEFAULT_DEEP_TIMEOUT_S = 45.0


def _deployment_for(mode: str) -> str:
    """Resolve the Azure OpenAI deployment name for a given mode.

    Env var priority per mode:
      fast   → AZURE_OPENAI_DEPLOYMENT_FAST → AZURE_OPENAI_DEPLOYMENT → "gpt-4o-mini"
      deep   → AZURE_OPENAI_DEPLOYMENT_DEEP → fast fallback
      legacy → AZURE_OPENAI_DEPLOYMENT → "gpt-4o-mini"
    """
    fast = os.environ.get("AZURE_OPENAI_DEPLOYMENT_FAST") or os.environ.get("AZURE_OPENAI_DEPLOYMENT") or "gpt-4o-mini"
    if mode == "fast":
        return fast
    if mode == "deep":
        return os.environ.get("AZURE_OPENAI_DEPLOYMENT_DEEP") or fast
    return os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")


# ---------------------------------------------------------------------------
# LLM call (with streaming + sync fallback)
# ---------------------------------------------------------------------------
def _call_azure_openai(
    ctx: ThesisContext,
    *,
    mode: str = "fast",
    stream_handler: Optional[Callable[[str], None]] = None,
    deadline_s: float = _DEFAULT_DEEP_TIMEOUT_S,
) -> tuple[dict, str, dict]:
    """Return (raw_dict, model_label, meta).

    ``stream_handler`` is an optional callable(delta_text: str) → None that is
    invoked as tokens stream in. If ``None`` the call is non-streaming.
    Falls back from streaming → sync if the streaming call errors.

    ``meta`` carries timing / mode info the caller can record.

    Reasoning models (o-family) are called **without** temperature and use
    ``max_completion_tokens`` semantics per Azure OpenAI.
    """
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    api_key = os.environ.get("AZURE_OPENAI_KEY")
    api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")

    if not (endpoint and api_key):
        raise RuntimeError("AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_KEY not set")

    if mode not in _VALID_MODES:
        mode = "fast"

    deployment = _deployment_for(mode)
    is_reasoning = deployment.lower().startswith(("o1", "o3", "o4"))
    # Reasoning models require ≥ 2024-12-01-preview on Azure OpenAI.
    # Auto-upgrade per-call so the rest of the app keeps its stable default.
    if is_reasoning:
        reasoning_version = os.environ.get(
            "AZURE_OPENAI_API_VERSION_REASONING", "2025-04-01-preview"
        )
        api_version = reasoning_version

    from openai import AzureOpenAI  # type: ignore
    import time as _t

    client = AzureOpenAI(
        azure_endpoint=endpoint,
        api_key=api_key,
        api_version=api_version,
    )

    meta: dict = {
        "mode": mode,
        "deployment": deployment,
        "is_reasoning": is_reasoning,
        "streamed": False,
        "retried": False,
        "latency_s": 0.0,
    }

    def _build_kwargs(retry_nudge: str = "") -> dict:
        user_payload = {
            "note": "All fields are real current values. Produce a trade thesis that cites them explicitly.",
            "mode_hint": mode,
            "context": ctx.to_dict(),
        }
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(user_payload, default=str)},
        ]
        if retry_nudge:
            messages.append({"role": "user", "content": retry_nudge})

        kwargs = dict(
            model=deployment,
            messages=messages,
            response_format={"type": "json_schema", "json_schema": THESIS_JSON_SCHEMA},
            max_completion_tokens=4000 if is_reasoning else 1400,
        )
        if not is_reasoning:
            # Reasoning models reject temperature in Azure OpenAI today.
            kwargs["temperature"] = 0.2
        return kwargs

    def _sync(retry_nudge: str = "") -> str:
        t0 = _t.monotonic()
        kwargs = _build_kwargs(retry_nudge)
        resp = client.chat.completions.create(**kwargs)
        meta["latency_s"] = round(_t.monotonic() - t0, 2)
        return resp.choices[0].message.content or "{}"

    def _streamed(retry_nudge: str = "") -> str:
        t0 = _t.monotonic()
        kwargs = _build_kwargs(retry_nudge)
        kwargs["stream"] = True
        stream = client.chat.completions.create(**kwargs)
        chunks: list[str] = []
        for event in stream:
            if _t.monotonic() - t0 > deadline_s:
                raise TimeoutError(
                    f"streaming exceeded deadline of {deadline_s:.0f}s"
                )
            choices = getattr(event, "choices", None) or []
            for ch in choices:
                delta = getattr(ch, "delta", None)
                if delta is None:
                    continue
                content = getattr(delta, "content", None)
                if content:
                    chunks.append(content)
                    if stream_handler is not None:
                        try:
                            stream_handler(content)
                        except Exception:
                            pass
        meta["streamed"] = True
        meta["latency_s"] = round(_t.monotonic() - t0, 2)
        return "".join(chunks) or "{}"

    def _parse(content: str) -> dict:
        return json.loads(content)

    # Try streaming → sync fallback
    try:
        if stream_handler is not None:
            content = _streamed()
        else:
            content = _sync()
        parsed = _parse(content)
        return parsed, f"Azure OpenAI: {deployment}", meta
    except (json.JSONDecodeError, TimeoutError, Exception) as exc:
        # If streaming specifically failed, retry once non-streaming.
        if stream_handler is not None and not isinstance(exc, json.JSONDecodeError):
            logger.info("Streaming call failed (%r), falling back to sync.", exc)
            meta["retried"] = True
            try:
                content = _sync()
                parsed = _parse(content)
                return parsed, f"Azure OpenAI (sync fallback): {deployment}", meta
            except Exception as exc2:
                exc = exc2
        # JSON decode or sync failure — one pointed retry.
        if isinstance(exc, json.JSONDecodeError):
            logger.warning("Malformed JSON from model, retrying once: %r", exc)
            meta["retried"] = True
            nudge = (
                "Your previous output was not valid JSON. Produce ONLY a JSON "
                "object matching the schema you were given. No code fences, no commentary."
            )
            content = _sync(retry_nudge=nudge)
            parsed = _parse(content)
            return parsed, f"Azure OpenAI (retry): {deployment}", meta
        raise


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
# Materiality — what constitutes a "meaningful" context change
# ---------------------------------------------------------------------------
def _materiality_fingerprint(ctx: ThesisContext) -> dict:
    """Return the minimal dict used to decide whether to regenerate.

    Kept deliberately small — we never want to burn tokens over
    millisecond noise. See ``context_changed_materially``.
    """
    return {
        "z": round(float(ctx.current_z), 2),
        "brent": round(float(ctx.latest_brent), 2),
        "wti": round(float(ctx.latest_wti), 2),
        "inv_4w_sign": 1 if ctx.inventory_4w_slope_bbls_per_day > 0 else (-1 if ctx.inventory_4w_slope_bbls_per_day < 0 else 0),
        "vol_bucket": _vol_bucket(ctx.vol_spread_1y_percentile),
        "inv_latest": round(float(ctx.inventory_current_bbls) / 1e6, 1),
    }


def _vol_bucket(percentile: float) -> str:
    """Coarse 3-bucket split of the 1y vol percentile."""
    if percentile < 33.0:
        return "low"
    if percentile > 66.0:
        return "high"
    return "mid"


def context_changed_materially(prev: dict | None, cur: dict, thresholds: dict | None = None) -> list[str]:
    """Return the list of reasons the new context is a meaningful change.

    Empty list = no material change → safe to serve cached thesis.
    """
    if prev is None:
        return ["first_run"]
    t = thresholds or {}
    d_z_thresh = float(t.get("d_z", 0.3))
    d_px_thresh_pct = float(t.get("d_px_pct", 1.5))
    d_inv_mbbl_thresh = float(t.get("d_inv_mbbl", 10.0))

    reasons: list[str] = []
    if abs(cur["z"] - prev["z"]) > d_z_thresh:
        reasons.append(f"Δ dislocation {prev['z']:+.2f} → {cur['z']:+.2f}")
    prev_brent = prev.get("brent", cur["brent"]) or 1.0
    if abs(cur["brent"] - prev_brent) / prev_brent * 100.0 > d_px_thresh_pct:
        reasons.append(f"Δ Brent {prev_brent:.2f} → {cur['brent']:.2f}")
    prev_wti = prev.get("wti", cur["wti"]) or 1.0
    if abs(cur["wti"] - prev_wti) / prev_wti * 100.0 > d_px_thresh_pct:
        reasons.append(f"Δ WTI {prev_wti:.2f} → {cur['wti']:.2f}")
    if cur["inv_4w_sign"] != prev.get("inv_4w_sign"):
        reasons.append(
            f"Inventory 4w slope sign flipped ({prev.get('inv_4w_sign')} → {cur['inv_4w_sign']})"
        )
    if cur["vol_bucket"] != prev.get("vol_bucket"):
        reasons.append(
            f"Vol regime {prev.get('vol_bucket')} → {cur['vol_bucket']}"
        )
    prev_inv = prev.get("inv_latest", cur["inv_latest"])
    if abs(cur["inv_latest"] - prev_inv) > d_inv_mbbl_thresh:
        reasons.append(
            f"New EIA release: inventory {prev_inv:,.1f} → {cur['inv_latest']:,.1f} Mbbl"
        )
    return reasons


# ---------------------------------------------------------------------------
# Thesis history (tail of the JSONL audit log)
# ---------------------------------------------------------------------------
def read_recent_theses(n: int = 10) -> list[dict]:
    """Return the most recent ``n`` thesis audit records, newest first."""
    if not _AUDIT_PATH.is_file():
        return []
    records: list[dict] = []
    try:
        with _AUDIT_PATH.open() as f:
            lines = f.readlines()
        for line in lines[-n * 3:]:  # read extra to filter malformed
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception:
                continue
    except Exception as exc:
        logger.debug("read audit failed: %r", exc)
        return []
    records.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
    return records[:n]


def diff_theses(prev_raw: dict | None, cur_raw: dict) -> list[str]:
    """Return a human-readable list of what changed between two thesis raws."""
    if prev_raw is None:
        return []
    diffs: list[str] = []
    if prev_raw.get("stance") != cur_raw.get("stance"):
        diffs.append(
            f"Stance flipped: {prev_raw.get('stance','?')} → {cur_raw.get('stance','?')}"
        )
    try:
        d = float(cur_raw.get("conviction_0_to_10", 0)) - float(prev_raw.get("conviction_0_to_10", 0))
    except Exception:
        d = 0.0
    if abs(d) >= 0.5:
        diffs.append(f"Confidence {d:+.1f} vs last thesis")

    prev_risks = set(prev_raw.get("invalidation_risks") or [])
    cur_risks = set(cur_raw.get("invalidation_risks") or [])
    new_risks = cur_risks - prev_risks
    dropped_risks = prev_risks - cur_risks
    for r in sorted(new_risks)[:3]:
        diffs.append(f"New risk: {r}")
    for r in sorted(dropped_risks)[:3]:
        diffs.append(f"Dropped: {r}")

    prev_events = {(c.get("event"), c.get("date")) for c in (prev_raw.get("catalyst_watchlist") or []) if isinstance(c, dict)}
    cur_events = {(c.get("event"), c.get("date")) for c in (cur_raw.get("catalyst_watchlist") or []) if isinstance(c, dict)}
    for e in sorted(cur_events - prev_events)[:3]:
        diffs.append(f"New catalyst: {e[0]} ({e[1]})")
    return diffs


def history_stats(records: list[dict]) -> dict:
    """Quick stats on the last N theses for a "Recent theses" summary line."""
    if not records:
        return {"n": 0, "long": 0, "short": 0, "flat": 0, "avg_conf": 0.0}
    stances = [r.get("thesis", {}).get("stance") for r in records]
    confs = [float(r.get("thesis", {}).get("conviction_0_to_10", 0) or 0) for r in records]
    return {
        "n": len(records),
        "long": stances.count("long_spread"),
        "short": stances.count("short_spread"),
        "flat": stances.count("flat"),
        "avg_conf": float(sum(confs) / len(confs)) if confs else 0.0,
    }


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
def generate_thesis(
    ctx: ThesisContext,
    *,
    log: bool = True,
    mode: str = "fast",
    stream_handler: Optional[Callable[[str], None]] = None,
) -> Thesis:
    """Return a validated :class:`Thesis`. Never raises.

    ``mode`` ∈ {"fast", "deep", "legacy"}. Auto-downgrades deep → fast on
    excessive latency. ``stream_handler`` receives partial text deltas
    as the API streams tokens; ``None`` uses non-streaming.
    """
    if mode not in _VALID_MODES:
        mode = "fast"
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fingerprint = ctx.fingerprint()
    model_label = "rule-based (fallback)"
    effective_mode = mode
    meta: dict = {"mode": mode, "streamed": False, "retried": False, "latency_s": 0.0}
    raw: dict = {}

    try:
        raw, model_label, meta = _call_azure_openai(
            ctx, mode=mode, stream_handler=stream_handler,
        )
        # Deep-mode guardrail: auto-downgrade on excessive latency
        if mode == "deep" and meta.get("latency_s", 0) > 20.0:
            logger.info("deep latency %.1fs > 20s — next run will downgrade to fast", meta["latency_s"])
    except Exception as exc:
        logger.info("Azure OpenAI unavailable, rule-based fallback: %r", exc)
        raw = _rule_based_fallback(ctx)
        raw.setdefault("data_caveats", []).append(f"Azure OpenAI fallback reason: {exc!r}")
        effective_mode = "rule-based"

    raw, notes = _apply_guardrails(raw, ctx)

    thesis = Thesis(
        raw=raw,
        generated_at=generated_at,
        source=model_label,
        model=meta.get("deployment") if "Azure" in model_label else None,
        context_fingerprint=fingerprint,
        guardrails_applied=notes,
        mode=effective_mode,
        latency_s=float(meta.get("latency_s", 0.0)),
        streamed=bool(meta.get("streamed", False)),
        retried=bool(meta.get("retried", False)),
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
    "context_changed_materially",
    "_materiality_fingerprint",
    "read_recent_theses",
    "diff_theses",
    "history_stats",
    "_deployment_for",
    "_apply_guardrails",
    "_rule_based_fallback",
]
