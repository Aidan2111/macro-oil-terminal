"""FastAPI application — fixture-backed, zero heavy imports.

This intentionally skips the sys.path shim into the root Streamlit
modules. Every endpoint returns plausible JSON fixtures so the Next.js
frontend renders with real-looking data on the first request. Real
provider wiring moves back in once the cutover lands and we can
iterate on it without blocking Aidan's demo.

Light imports only: FastAPI + stdlib. Container warmup is <2 s.
"""

from __future__ import annotations

import json
import math
import os
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """Return the FastAPI app. Kept as a factory so existing tests
    that do ``from backend.main import create_app`` still import."""
    a = FastAPI(
        title="Macro Oil Terminal API",
        version="0.2.0",
        description=(
            "Fixture-backed backend during React cutover. All endpoints return "
            "deterministic, plausible JSON so the frontend renders immediately. "
            "Real provider wiring returns post-cutover."
        ),
    )
    a.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    return a


app = create_app()


# ---------------------------------------------------------------------------
# Deterministic fixture helpers
# ---------------------------------------------------------------------------

_RNG = random.Random(42)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _series(base: float, days: int, noise: float = 0.3) -> list[dict[str, Any]]:
    """Deterministic pseudo-random series; new RNG each call so calls are
    independent but stable across process restarts (seeded)."""
    rng = random.Random(42 + int(base))
    out: list[dict[str, Any]] = []
    today = datetime.now(timezone.utc).date()
    val = base
    for i in range(days):
        val += (rng.random() - 0.5) * noise
        day = today - timedelta(days=days - i - 1)
        out.append({"date": day.isoformat(), "value": round(val, 4)})
    return out


# ---------------------------------------------------------------------------
# Light endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
def health_root() -> dict[str, Any]:
    return {"status": "ok", "mode": "fixture"}


@app.get("/api/health")
def health_api() -> dict[str, Any]:
    return {"status": "ok", "mode": "fixture"}


@app.get("/api/build-info")
def build_info() -> dict[str, Any]:
    return {
        "sha": os.environ.get("BUILD_SHA", "dev"),
        "sha_short": os.environ.get("BUILD_VERSION", "dev"),
        "time": os.environ.get("BUILD_TIME", _utcnow_iso()),
        "region": os.environ.get("BACKEND_REGION", "canadaeast"),
        "mode": "fixture",
    }


# ---------------------------------------------------------------------------
# Spread / stretch
# ---------------------------------------------------------------------------


@app.get("/api/spread")
def get_spread() -> dict[str, Any]:
    brent = _series(82.4, 90, noise=0.6)
    wti = _series(78.1, 90, noise=0.5)
    series = [
        {
            "date": brent[i]["date"],
            "brent": brent[i]["value"],
            "wti": wti[i]["value"],
            "spread": round(brent[i]["value"] - wti[i]["value"], 4),
        }
        for i in range(len(brent))
    ]
    latest = series[-1]
    spread_values = [p["spread"] for p in series[-90:]]
    mean = sum(spread_values) / len(spread_values)
    sd = math.sqrt(sum((v - mean) ** 2 for v in spread_values) / len(spread_values))
    stretch = round((latest["spread"] - mean) / sd, 3) if sd > 0 else 0.0
    return {
        "brent_price": latest["brent"],
        "wti_price": latest["wti"],
        "spread_usd": latest["spread"],
        "stretch": stretch,
        "stretch_band": _band_for(abs(stretch)),
        "series": series,
        "source": "fixture",
        "fetched_at": _utcnow_iso(),
    }


def _band_for(abs_z: float) -> str:
    if abs_z < 0.7:
        return "Calm"
    if abs_z < 1.3:
        return "Normal"
    if abs_z < 2.3:
        return "Stretched"
    if abs_z < 3.2:
        return "Very Stretched"
    return "Extreme"


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------


@app.get("/api/inventory")
def get_inventory() -> dict[str, Any]:
    commercial = _series(430.0, 104, noise=4.0)  # Mbbl, 2y weekly-ish
    cushing = _series(28.0, 104, noise=0.6)
    spr = _series(380.0, 104, noise=1.5)
    latest = commercial[-1]
    forecast_days = 365
    slope_per_day = (commercial[-1]["value"] - commercial[-30]["value"]) / 30.0
    today = datetime.now(timezone.utc).date()
    projected_floor_date = None
    if slope_per_day < 0:
        days_to_300 = (300.0 - latest["value"]) / slope_per_day
        if 0 < days_to_300 < forecast_days:
            projected_floor_date = (today + timedelta(days=int(days_to_300))).isoformat()
    return {
        "commercial_mbbl": latest["value"],
        "cushing_mbbl": cushing[-1]["value"],
        "spr_mbbl": spr[-1]["value"],
        "commercial_series": commercial,
        "cushing_series": cushing,
        "spr_series": spr,
        "slope_per_day_mbbl": round(slope_per_day, 4),
        "projected_floor_date": projected_floor_date,
        "source": "fixture",
        "fetched_at": _utcnow_iso(),
    }


# ---------------------------------------------------------------------------
# CFTC positioning
# ---------------------------------------------------------------------------


@app.get("/api/cftc")
def get_cftc() -> dict[str, Any]:
    history = _series(200000, 156, noise=4000.0)  # 3y weekly
    mean = sum(p["value"] for p in history) / len(history)
    sd = math.sqrt(sum((p["value"] - mean) ** 2 for p in history) / len(history))
    latest_net = history[-1]["value"]
    z = round((latest_net - mean) / sd, 2) if sd > 0 else 0.0
    return {
        "managed_money_net": int(latest_net),
        "commercial_net": -int(latest_net * 1.05),
        "mm_zscore_3y": z,
        "history": history,
        "report_date": history[-1]["date"],
        "source": "fixture",
        "fetched_at": _utcnow_iso(),
    }


# ---------------------------------------------------------------------------
# Fleet
# ---------------------------------------------------------------------------


_FIXTURE_VESSELS = [
    {"mmsi": 366999001, "name": "ATLANTIC PIONEER", "lat": 29.76, "lon": -95.37, "flag_category": "domestic", "country": "USA"},
    {"mmsi": 371234001, "name": "GULF RANGER", "lat": 27.95, "lon": -93.10, "flag_category": "domestic", "country": "USA"},
    {"mmsi": 311000022, "name": "CRIMSON STAR", "lat": 51.50, "lon": 3.10, "flag_category": "shadow", "country": "Bahamas"},
    {"mmsi": 353000011, "name": "NIGHT ORCHID", "lat": 1.35, "lon": 103.82, "flag_category": "shadow", "country": "Panama"},
    {"mmsi": 636000091, "name": "DAWN CARRIER", "lat": 5.55, "lon": 53.00, "flag_category": "shadow", "country": "Liberia"},
    {"mmsi": 273000015, "name": "VOSTOK STORM", "lat": 45.10, "lon": 36.55, "flag_category": "sanctioned", "country": "Russia"},
    {"mmsi": 422000203, "name": "PERSIAN BREEZE", "lat": 25.30, "lon": 57.80, "flag_category": "sanctioned", "country": "Iran"},
    {"mmsi": 775000044, "name": "CARACAS DAWN", "lat": 10.05, "lon": -65.20, "flag_category": "sanctioned", "country": "Venezuela"},
    {"mmsi": 564000567, "name": "EASTERN PROMISE", "lat": 22.30, "lon": 114.20, "flag_category": "other", "country": "Singapore"},
    {"mmsi": 431000123, "name": "SAKURA MARU", "lat": 35.65, "lon": 139.78, "flag_category": "other", "country": "Japan"},
    {"mmsi": 248000999, "name": "MEDITERRANEAN SUN", "lat": 36.14, "lon": 14.26, "flag_category": "other", "country": "Malta"},
    {"mmsi": 538000456, "name": "MARSHALL ORION", "lat": 20.10, "lon": 166.50, "flag_category": "other", "country": "Marshall Islands"},
]


@app.get("/api/fleet/snapshot")
def fleet_snapshot() -> dict[str, Any]:
    return {
        "vessels": _FIXTURE_VESSELS,
        "n_vessels": len(_FIXTURE_VESSELS),
        "last_message_seconds_ago": 42,
        "source": "fixture",
        "fetched_at": _utcnow_iso(),
    }


@app.get("/api/fleet/categories")
def fleet_categories() -> dict[str, Any]:
    counts: dict[str, int] = {}
    for v in _FIXTURE_VESSELS:
        counts[v["flag_category"]] = counts.get(v["flag_category"], 0) + 1
    cargo_mbbl = {k: round(v * 1.4, 2) for k, v in counts.items()}
    return {"vessel_counts": counts, "cargo_mbbl": cargo_mbbl, "source": "fixture"}


# ---------------------------------------------------------------------------
# Trade thesis
# ---------------------------------------------------------------------------


_FIXTURE_THESIS = {
    "context_fingerprint": "fixture-2026-04-24",
    "generated_at": _utcnow_iso(),
    "mode": "fast",
    "model": "fixture",
    "plain_english_headline": (
        "Brent is trading a bit more expensive than WTI right now. The gap "
        "is stretched enough to bet on it narrowing over the next few weeks."
    ),
    "stance": "LONG_SPREAD",
    "conviction_0_to_10": 6,
    "time_horizon_days": 14,
    "reasoning_summary": (
        "Brent–WTI spread is trading ~2.1× above its 90-day normal. "
        "Inventories are drawing in Cushing at ~0.2 Mbbl/day; CFTC managed-money "
        "net is neutral. Historical mean-reversion within 2–3 weeks is the base case."
    ),
    "key_drivers": [
        "Spread Stretch 2.1 — Stretched band",
        "Cushing inventory drawing slowly",
        "CFTC positioning neutral, no crowded trade to fight",
        "EIA release in 34h — watch for surprise",
    ],
    "invalidation_risks": [
        "Cushing inventory build > 1 Mbbl in next EIA report",
        "OPEC+ emergency cut announcement",
        "Hurricane-induced refinery shutdown in PADD 3",
    ],
    "data_caveats": [],
    "instruments": [
        {
            "tier": 1,
            "name": "Paper position",
            "legs": "BZ=F long / CL=F short, 1:1 ratio",
            "symbol": "BZ=F/CL=F",
            "suggested_pct_of_capital": 0.0,
            "sizing_method": "paper",
            "size_usd": 0,
            "rationale": "Track the idea without capital at risk.",
        },
        {
            "tier": 2,
            "name": "USO / BNO ETF spread",
            "legs": "BNO long / USO short, beta-adjusted",
            "symbol": "BNO/USO",
            "suggested_pct_of_capital": 5.0,
            "sizing_method": "volatility_scaled",
            "size_usd": 5000,
            "rationale": "Retail-friendly access via ETFs; no futures account needed.",
        },
        {
            "tier": 3,
            "name": "Futures spread",
            "legs": "BZ=F long 1 contract / CL=F short 1 contract",
            "symbol": "BZ=F/CL=F",
            "suggested_pct_of_capital": 10.0,
            "sizing_method": "kelly",
            "size_usd": 10000,
            "rationale": "Pure spread exposure; margin efficient via inter-commodity spread credit.",
        },
    ],
    "checklist": [
        {"key": "stop_in_place", "label": "Stop in place", "auto_check": None},
        {"key": "vol_clamp_ok", "label": "Size within vol-regime cap", "auto_check": True},
        {"key": "half_life_ack", "label": "I understand the implied half-life is ~7 days.", "auto_check": None},
        {"key": "catalyst_clear", "label": "No EIA/OPEC catalyst within 24h", "auto_check": False},
        {"key": "no_conflicting_recent_thesis", "label": "No conflicting thesis in last 5 sessions", "auto_check": None},
    ],
    "materiality_flat": False,
    "applied_guardrails": ["vol_regime_ok"],
}


@app.get("/api/thesis/latest")
def thesis_latest() -> dict[str, Any]:
    return {"thesis": _FIXTURE_THESIS, "source": "fixture"}


@app.get("/api/thesis/history")
def thesis_history(limit: int = 30) -> dict[str, Any]:
    if limit < 1 or limit > 200:
        return JSONResponse(status_code=422, content={"detail": "limit out of range"})
    history = [_FIXTURE_THESIS for _ in range(min(limit, 30))]
    return {"theses": history, "count": len(history), "source": "fixture"}


async def _sse_stream_thesis():
    """Stream the fixture thesis progressively as SSE frames."""
    import asyncio

    yield f"event: progress\ndata: {json.dumps({'stage': 'fetching_context', 'pct': 10})}\n\n"
    await asyncio.sleep(0.3)
    yield f"event: progress\ndata: {json.dumps({'stage': 'calling_llm', 'pct': 40})}\n\n"
    await asyncio.sleep(0.5)
    for chunk in _FIXTURE_THESIS["reasoning_summary"].split(". "):
        payload = json.dumps({"text": chunk + ". "})
        yield f"event: delta\ndata: {payload}\n\n"
        await asyncio.sleep(0.15)
    yield f"event: progress\ndata: {json.dumps({'stage': 'applying_guardrails', 'pct': 90})}\n\n"
    await asyncio.sleep(0.2)
    done = {"thesis": _FIXTURE_THESIS, "applied_guardrails": _FIXTURE_THESIS["applied_guardrails"], "materiality_flat": False}
    yield f"event: done\ndata: {json.dumps(done)}\n\n"


@app.post("/api/thesis/generate")
async def thesis_generate(req: Request):
    body = await req.json() if req.headers.get("content-length") else {}
    mode = body.get("mode", "fast")
    if mode not in ("fast", "deep"):
        return JSONResponse(status_code=422, content={"detail": "mode must be 'fast' or 'deep'"})
    portfolio = body.get("portfolio_usd")
    if portfolio is not None and (not isinstance(portfolio, (int, float)) or portfolio <= 0):
        return JSONResponse(status_code=422, content={"detail": "portfolio_usd must be positive"})
    return StreamingResponse(_sse_stream_thesis(), media_type="text/event-stream")


@app.post("/api/thesis/regenerate")
async def thesis_regenerate(req: Request):
    return await thesis_generate(req)


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------


@app.post("/api/backtest")
async def backtest(req: Request) -> dict[str, Any]:
    body = await req.json() if req.headers.get("content-length") else {}
    equity = _series(10000, 365, noise=80.0)
    rng = random.Random(123)
    trades = []
    for i in range(48):
        trades.append(
            {
                "entry_date": (datetime.now(timezone.utc).date() - timedelta(days=365 - i * 7)).isoformat(),
                "exit_date": (datetime.now(timezone.utc).date() - timedelta(days=365 - i * 7 - 5)).isoformat(),
                "entry_price": round(80 + rng.random() * 10, 2),
                "exit_price": round(80 + rng.random() * 10, 2),
                "pnl_usd": round((rng.random() - 0.45) * 400, 2),
            }
        )
    total_pnl = sum(t["pnl_usd"] for t in trades)
    wins = sum(1 for t in trades if t["pnl_usd"] > 0)
    return {
        "sharpe": 1.42,
        "sortino": 2.08,
        "calmar": 0.85,
        "var_95": -420.0,
        "es_95": -680.0,
        "max_drawdown_usd": -1100.0,
        "hit_rate": round(wins / len(trades), 3),
        "n_trades": len(trades),
        "total_pnl_usd": round(total_pnl, 2),
        "equity_curve": equity,
        "trades": trades,
        "rolling_12m_sharpe": 1.35,
        "source": "fixture",
        "params_echo": body,
    }


# ---------------------------------------------------------------------------
# Positions (Alpaca paper — fixtures until real wire-up)
# ---------------------------------------------------------------------------


_FIXTURE_POSITIONS = [
    {
        "symbol": "BNO",
        "qty": 100,
        "side": "long",
        "avg_entry_price": 32.10,
        "current_price": 32.84,
        "market_value": 3284.00,
        "unrealized_pl": 74.00,
        "unrealized_plpc": 0.023,
    },
    {
        "symbol": "USO",
        "qty": -120,
        "side": "short",
        "avg_entry_price": 74.20,
        "current_price": 73.10,
        "market_value": -8772.00,
        "unrealized_pl": 132.00,
        "unrealized_plpc": 0.015,
    },
]


@app.get("/api/positions")
def positions() -> dict[str, Any]:
    return {"positions": _FIXTURE_POSITIONS, "count": len(_FIXTURE_POSITIONS), "source": "fixture"}


@app.get("/api/positions/account")
def positions_account() -> dict[str, Any]:
    return {
        "buying_power": 91940.00,
        "cash": 85000.00,
        "equity": 100206.00,
        "portfolio_value": 100206.00,
        "currency": "USD",
        "status": "ACTIVE",
        "paper": True,
        "source": "fixture",
    }


@app.get("/api/positions/orders")
def positions_orders(status: str = "open") -> dict[str, Any]:
    return {"orders": [], "status": status, "source": "fixture"}


@app.post("/api/positions/execute")
async def positions_execute(req: Request):
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Paper execution is pending reconnect to live Alpaca backend. UI shows expected behaviour; real orders will fire post-cutover.",
            "mode": "fixture",
        },
    )
