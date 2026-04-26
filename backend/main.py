"""FastAPI application — real-data-first, lazy-imported providers.

Module-level imports are stdlib + FastAPI only so container warmup is
<2 s. Heavy provider imports (pandas, yfinance, statsmodels, openai,
alpaca-py) live inside route handlers so the worker only pays the
import cost on first hit, never on cold-start health probes.

Per Aidan's overnight directive: NO silent fixture fallback. When a
provider is unreachable or a key is missing, the route returns a 503
with a friendly `detail` string. The React UI's ErrorState components
surface a banner + retry button. Fixture data is reserved for the
explicit ``/api/<route>/fixture`` debug endpoints used during
provisioning; the canonical endpoints always go to real upstream.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import random
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, TypeVar

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from backend.security import (
    enforce_execute_rate_limit,
    require_execute_origin,
)


# ---------------------------------------------------------------------------
# Tiny TTL cache — module-level, threadsafe, exception-skipping
# ---------------------------------------------------------------------------

_T = TypeVar("_T")


class _TTLCache:
    """Single-slot per-key TTL cache. Thread-safe. Exceptions never cache."""

    def __init__(self) -> None:
        self._slots: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get_or_compute(self, key: str, ttl: float, factory: Callable[[], _T]) -> _T:
        now = time.monotonic()
        with self._lock:
            slot = self._slots.get(key)
            if slot is not None and slot[0] > now:
                return slot[1]
        value = factory()
        with self._lock:
            self._slots[key] = (time.monotonic() + ttl, value)
        return value

    def invalidate(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._slots.clear()
            else:
                self._slots.pop(key, None)


_CACHE = _TTLCache()


def _provider_error(provider: str, exc: Exception, hint: str | None = None) -> JSONResponse:
    """Uniform 503 envelope for upstream provider failures.

    The React UI surfaces ``detail`` via its ErrorState component, which
    renders a friendly banner + retry button. ``provider`` lets the
    panel disambiguate (e.g. "yfinance is rate-limited", not the
    generic "something went wrong").
    """
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                f"{provider} is temporarily unavailable: "
                f"{type(exc).__name__}: {exc}"
                + (f". {hint}" if hint else "")
            ),
            "provider": provider,
            "code": "provider_unavailable",
        },
    )


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    """Return the FastAPI app. Kept as a factory so existing tests
    that do ``from backend.main import create_app`` still import."""
    a = FastAPI(
        title="Macro Oil Terminal API",
        version="0.3.0",
        description=(
            "Real-data backend. Lazy-imports providers so cold-start stays <2s; "
            "every canonical endpoint hits live upstreams (yfinance, EIA, FRED, "
            "CFTC, AISStream, Alpaca paper, Azure OpenAI). On upstream failure "
            "the route returns 503 with a friendly detail; the React UI shows a "
            "banner + retry. Fixture endpoints under /api/<x>/fixture remain for "
            "debug only."
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
    # Phase 1 wired every canonical endpoint to a real upstream
    # provider; the "fixture" label is a leftover from the cutover-week
    # branding and was misleading the healthcheck. Flip to "live" now
    # that the route surface is real-data first. /api/<x>/fixture debug
    # endpoints still exist for provisioning, but the canonical surface
    # never serves fixtures.
    return {"status": "ok", "mode": "live"}


@app.get("/api/health")
def health_api() -> dict[str, Any]:
    return {"status": "ok", "mode": "live"}


@app.get("/api/build-info")
def build_info() -> dict[str, Any]:
    return {
        "sha": os.environ.get("BUILD_SHA", "dev"),
        "sha_short": os.environ.get("BUILD_VERSION", "dev"),
        "time": os.environ.get("BUILD_TIME", _utcnow_iso()),
        "region": os.environ.get("BACKEND_REGION", "canadaeast"),
        "mode": "live",
    }


# ---------------------------------------------------------------------------
# Spread / stretch
# ---------------------------------------------------------------------------


def _fixture_spread() -> dict[str, Any]:
    """Deterministic fixture used by /api/spread/fixture (debug only)."""
    brent = _series(82.4, 90, noise=0.6)
    wti = _series(78.1, 90, noise=0.5)
    spread_values: list[float] = []
    history: list[dict[str, Any]] = []
    for i in range(len(brent)):
        sp = round(brent[i]["value"] - wti[i]["value"], 4)
        spread_values.append(sp)
        history.append(
            {
                "date": brent[i]["date"],
                "brent": brent[i]["value"],
                "wti": wti[i]["value"],
                "spread": sp,
                "z_score": None,
            }
        )
    mean = sum(spread_values) / len(spread_values)
    sd = math.sqrt(sum((v - mean) ** 2 for v in spread_values) / len(spread_values))
    if sd > 0:
        for h in history:
            h["z_score"] = round((float(h["spread"]) - mean) / sd, 3)
    latest = history[-1]
    stretch = float(latest["z_score"] or 0.0)
    return {
        "brent": latest["brent"],
        "wti": latest["wti"],
        "spread": latest["spread"],
        "stretch": stretch,
        "stretch_band": _band_for(abs(stretch)),
        "as_of": _utcnow_iso(),
        "source": "fixture",
        "history": history,
        "brent_price": latest["brent"],
        "wti_price": latest["wti"],
        "spread_usd": latest["spread"],
        "series": history,
        "fetched_at": _utcnow_iso(),
    }


def _real_spread(history_bars: int = 90) -> dict[str, Any]:
    """Hit yfinance via the legacy provider stack and return a
    SpreadLiveResponse-shaped payload."""
    # Lazy import — keep cold-start fast.
    from backend.services.spread_service import get_spread_response

    resp = get_spread_response(history_bars=history_bars)
    # Pydantic model → plain dict; keep extra legacy aliases the
    # frontend tickers and macro charts already consume.
    base = resp.model_dump(mode="json")
    history = base.get("history", []) or []
    return {
        **base,
        "brent_price": base.get("brent"),
        "wti_price": base.get("wti"),
        "spread_usd": base.get("spread"),
        "series": history,
        "fetched_at": _utcnow_iso(),
    }


@app.get("/api/spread")
def get_spread() -> Any:
    """Live Brent–WTI prices + spread + dislocation Z + history.

    Cached 30s (per Aidan's directive). Returns 503 with a friendly
    detail when yfinance / Twelve Data / Polygon all fail; the React
    ticker tape and macro charts surface this as a banner.
    """
    try:
        return _CACHE.get_or_compute("spread", 30.0, _real_spread)
    except Exception as exc:  # pragma: no cover — sandbox-tested below
        return _provider_error(
            "yfinance",
            exc,
            hint="Brent/WTI futures pricing is the upstream; retry in ~30s.",
        )


@app.get("/api/spread/fixture")
def get_spread_fixture() -> dict[str, Any]:
    """Deterministic fixture for debug only — never auto-served."""
    return _fixture_spread()


async def _sse_spread_heartbeat():
    """Heartbeat-only SSE stream for the ticker tape. The TickerTape
    component refetches its react-query cache on each onmessage. We
    emit one immediate frame, then a 20-s ping so the channel stays
    open without churning the network. Backend has no live tick yet,
    so this is best-effort."""
    yield ": connected\n\n"
    while True:
        await asyncio.sleep(20)
        yield f"data: {json.dumps({'tick': _utcnow_iso()})}\n\n"


@app.get("/api/spread/stream")
async def spread_stream():
    return StreamingResponse(
        _sse_spread_heartbeat(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


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


def _real_inventory() -> dict[str, Any]:
    """Hit EIA primary / FRED fallback via providers.inventory and
    return an InventoryLiveResponse-shaped payload (raw bbls + history
    + depletion forecast)."""
    from backend.services.inventory_service import get_inventory_response

    resp = get_inventory_response()
    base = resp.model_dump(mode="json")
    history = base.get("history", []) or []
    latest = base
    return {
        **base,
        # Legacy aliases retained for older parts of the repo.
        "commercial_mbbl": (latest.get("commercial_bbls") or 0) / 1_000_000,
        "cushing_mbbl": (latest.get("cushing_bbls") or 0) / 1_000_000,
        "spr_mbbl": (latest.get("spr_bbls") or 0) / 1_000_000,
        "commercial_series": history,
        "cushing_series": history,
        "spr_series": history,
        "fetched_at": _utcnow_iso(),
    }


def _fixture_inventory() -> dict[str, Any]:
    # Frontend InventoryLiveResponse expects raw bbl counts and a
    # `history: InventoryPoint[]` series with date + commercial_bbls
    # + spr_bbls + cushing_bbls + total_bbls per row. Easier to seed
    # in Mbbl, then multiply at the end.
    commercial = _series(430.0, 104, noise=4.0)  # Mbbl, 2y weekly-ish
    cushing = _series(28.0, 104, noise=0.6)
    spr = _series(380.0, 104, noise=1.5)
    # Source seeds are in MMbbl (millions of barrels). Frontend wants
    # raw bbls — and its TickerTape formatter divides by 1_000_000 in
    # two steps to display "430 Mbbl" (its label is the trader-style
    # short for millions). Multiplier 1e6 keeps the magnitudes right.
    history = [
        {
            "date": commercial[i]["date"],
            "commercial_bbls": int(commercial[i]["value"] * 1_000_000),
            "cushing_bbls": int(cushing[i]["value"] * 1_000_000),
            "spr_bbls": int(spr[i]["value"] * 1_000_000),
            "total_bbls": int(
                (commercial[i]["value"] + cushing[i]["value"] + spr[i]["value"]) * 1_000_000
            ),
        }
        for i in range(len(commercial))
    ]
    latest = history[-1]
    slope_per_day = (commercial[-1]["value"] - commercial[-30]["value"]) / 30.0
    today = datetime.now(timezone.utc).date()
    projected_floor_date = None
    if slope_per_day < 0:
        days_to_300 = (300.0 - commercial[-1]["value"]) / slope_per_day
        if 0 < days_to_300 < 365:
            projected_floor_date = (today + timedelta(days=int(days_to_300))).isoformat()
    forecast = {
        "daily_depletion_bbls": int(abs(slope_per_day) * 1_000_000),
        "weekly_depletion_bbls": int(abs(slope_per_day) * 1_000_000 * 7),
        "projected_floor_date": projected_floor_date,
        "r_squared": 0.71,
        "floor_bbls": 300_000_000,
    }
    return {
        # Frontend-shape fields:
        "commercial_bbls": latest["commercial_bbls"],
        "cushing_bbls": latest["cushing_bbls"],
        "spr_bbls": latest["spr_bbls"],
        "total_bbls": latest["total_bbls"],
        "as_of": _utcnow_iso(),
        "source": "fixture",
        "history": history,
        "forecast": forecast,
        # Legacy aliases — kept so older callers don't break
        "commercial_mbbl": commercial[-1]["value"],
        "cushing_mbbl": cushing[-1]["value"],
        "spr_mbbl": spr[-1]["value"],
        "commercial_series": commercial,
        "cushing_series": cushing,
        "spr_series": spr,
        "slope_per_day_mbbl": round(slope_per_day, 4),
        "projected_floor_date": projected_floor_date,
        "fetched_at": _utcnow_iso(),
    }


@app.get("/api/inventory")
def get_inventory() -> Any:
    """Live commercial / Cushing / SPR stocks + forecast.

    Cached 1 hour (EIA only releases weekly). 503 with friendly detail
    when both EIA primary and FRED fallback are unreachable.
    """
    try:
        return _CACHE.get_or_compute("inventory", 3600.0, _real_inventory)
    except Exception as exc:
        return _provider_error(
            "EIA/FRED",
            exc,
            hint="EIA is the primary; FRED is the fallback. Retry in ~1m.",
        )


@app.get("/api/inventory/fixture")
def get_inventory_fixture() -> dict[str, Any]:
    return _fixture_inventory()


# ---------------------------------------------------------------------------
# CFTC positioning
# ---------------------------------------------------------------------------


def _real_cftc() -> dict[str, Any]:
    """Pull weekly Commitments-of-Traders for WTI managed-money +
    producer + swap-dealer nets via the legacy CFTC provider."""
    from backend.services.cftc_service import get_cftc_response

    resp = get_cftc_response()
    return resp.model_dump(mode="json")


def _fixture_cftc() -> dict[str, Any]:
    history = _series(200000, 156, noise=4000.0)
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


@app.get("/api/cftc")
def get_cftc() -> Any:
    """Live CFTC Commitments of Traders — WTI managed-money / producer /
    swap-dealer nets + 3y history + Z-score of MM net.

    Cached 24h (CFTC publishes Friday 3:30pm ET; weekly cadence).
    """
    try:
        return _CACHE.get_or_compute("cftc", 24 * 3600.0, _real_cftc)
    except Exception as exc:
        return _provider_error(
            "CFTC",
            exc,
            hint="Weekly COT flat-file from cftc.gov. Retry next Friday at 3:30pm ET.",
        )


@app.get("/api/cftc/fixture")
def get_cftc_fixture() -> dict[str, Any]:
    return _fixture_cftc()


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


def _real_fleet_snapshot() -> dict[str, Any]:
    """Pull the current memory-cache from fleet_service. The producer
    task is started once via _ensure_producer_running() — first
    request triggers the websocket subscribe."""
    from backend.services import fleet_service

    fleet_service._ensure_producer_running()
    vessels = fleet_service.get_snapshot()
    return {
        "vessels": vessels,
        "n_vessels": len(vessels),
        "last_message_seconds_ago": 0,
        "source": "aisstream" if os.environ.get("AISSTREAM_API_KEY") else "historical",
        "fetched_at": _utcnow_iso(),
    }


def _real_fleet_categories() -> dict[str, Any]:
    from backend.services import fleet_service

    fleet_service._ensure_producer_running()
    return fleet_service.get_categories()


@app.get("/api/fleet/snapshot")
def fleet_snapshot() -> Any:
    """Live AISStream-derived crude-tanker positions. Falls through to
    the historical snapshot when the producer hasn't received any
    real frames yet (e.g. cold start)."""
    try:
        return _CACHE.get_or_compute("fleet_snapshot", 5.0, _real_fleet_snapshot)
    except Exception as exc:
        return _provider_error("aisstream", exc, hint="Check AISSTREAM_API_KEY app setting.")


@app.get("/api/fleet/categories")
def fleet_categories() -> Any:
    try:
        return _CACHE.get_or_compute("fleet_categories", 30.0, _real_fleet_categories)
    except Exception as exc:
        return _provider_error("aisstream", exc)


@app.get("/api/fleet/vessels")
async def fleet_vessels_stream():
    """SSE stream of live vessel position deltas filtered to crude
    tankers. Frontend's FleetGlobe consumes via EventSource and
    incrementally re-renders without refetching the full snapshot."""
    from backend.services import fleet_service

    fleet_service._ensure_producer_running()

    async def _gen():
        q = await fleet_service.subscribe()
        try:
            yield ": connected\n\n"
            while True:
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"event: vessel\ndata: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    yield f"event: ping\ndata: {json.dumps({'ts': _utcnow_iso()})}\n\n"
        finally:
            await fleet_service.unsubscribe(q)

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/fleet/snapshot/fixture")
def fleet_snapshot_fixture() -> dict[str, Any]:
    return {
        "vessels": _FIXTURE_VESSELS,
        "n_vessels": len(_FIXTURE_VESSELS),
        "last_message_seconds_ago": 42,
        "source": "fixture",
        "fetched_at": _utcnow_iso(),
    }


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
            "symbol": "BZ=F/CL=F",
            "suggested_size_pct": 0.0,
            "worst_case_per_unit": "$0 — paper only, no capital at risk",
            "rationale": "Track the idea without capital at risk.",
        },
        {
            "tier": 2,
            "name": "USO / BNO ETF spread",
            "symbol": "BNO/USO",
            "suggested_size_pct": 5.0,
            "worst_case_per_unit": "~$120 per $5k notional at 2σ adverse move",
            "rationale": "Retail-friendly access via ETFs; no futures account needed.",
        },
        {
            "tier": 3,
            "name": "Futures spread",
            "symbol": "BZ=F/CL=F",
            "suggested_size_pct": 10.0,
            "worst_case_per_unit": "~$2,000 per 1-contract spread at 2σ adverse move",
            "rationale": "Pure spread exposure; margin efficient via inter-commodity spread credit.",
        },
    ],
    "checklist": [
        {"key": "stop_in_place", "prompt": "I have a stop at ±2σ spread move from entry.", "auto_check": None},
        {"key": "vol_clamp_ok", "prompt": "Spread realised vol is below the 1y 85th percentile.", "auto_check": True},
        {"key": "half_life_ack", "prompt": "I understand the implied half-life is ~7 days.", "auto_check": None},
        {"key": "catalyst_clear", "prompt": "No EIA release within the next 24 hours.", "auto_check": False},
        {"key": "no_conflicting_recent_thesis", "prompt": "No stance flip in the last 5 thesis entries.", "auto_check": None},
    ],
    "materiality_flat": False,
    "applied_guardrails": ["vol_regime_ok"],
}


def _wrap_thesis_audit_record(t: dict[str, Any]) -> dict[str, Any]:
    """Shape `_FIXTURE_THESIS` into the `ThesisAuditRecord` the
    frontend types expect: a row with `timestamp`/`source`/`model`/
    `context_fingerprint`/`context`/`thesis: ThesisRaw` plus
    decorated `instruments` and `checklist`. The frontend's
    `ThesisLatestResponse` type also requires an `empty` boolean.
    """
    raw_thesis = {
        "stance": t["stance"],
        "conviction_0_to_10": t["conviction_0_to_10"],
        "time_horizon_days": t["time_horizon_days"],
        "thesis_summary": t["reasoning_summary"],
        "plain_english_headline": t["plain_english_headline"],
        "key_drivers": t.get("key_drivers", []),
        "invalidation_risks": t.get("invalidation_risks", []),
        "data_caveats": t.get("data_caveats", []),
        "reasoning_summary": t["reasoning_summary"],
    }
    return {
        "timestamp": t["generated_at"],
        "source": "fixture",
        "model": t.get("model", "fixture"),
        "context_fingerprint": t["context_fingerprint"],
        "context": {
            "current_z": 2.1,
            "hours_to_next_eia": 34,
            "stretch_band": "Stretched",
        },
        "thesis": raw_thesis,
        "guardrails": t.get("applied_guardrails", []),
        "instruments": t.get("instruments", []),
        "checklist": t.get("checklist", []),
    }


def _real_thesis_latest() -> dict[str, Any]:
    """Read the most recent audit record written by trade_thesis.

    Q1 data-quality slice: thread an OPTIONAL ``lineage`` block onto the
    response so the React hero card can show "yfinance, BZ=F+CL=F front-
    month, fetched 2m ago, n=251" as a tooltip on hover. Lineage is a
    NEW field — not in the original ThesisLatestResponse schema — so the
    frontend treats it as optional.

    # Q1-DATA-QUALITY-THESIS-LINEAGE
    """
    from backend.services.thesis_service import get_latest_thesis

    rec = get_latest_thesis()
    base: dict[str, Any]
    if rec is None:
        base = {"thesis": None, "empty": True, "source": "audit_log"}
    else:
        base = {"thesis": rec, "empty": False, "source": "audit_log"}

    # Attach spread lineage when spread_service has been hit at least
    # once. The hero card's spread value is the headline numeric, so
    # lineage on yfinance is the most actionable.
    try:
        from backend.services.spread_service import get_last_fetch_state

        snap = get_last_fetch_state()
        last_good = snap.get("last_good_at")
        n_obs = snap.get("n_obs")
        if last_good is not None:
            base["lineage"] = {
                "source": "yfinance",
                "symbol": "BZ=F+CL=F",
                "asof": last_good.isoformat() if hasattr(last_good, "isoformat") else None,
                "n_obs": n_obs,
                "latency_ms": snap.get("latency_ms"),
            }
    except Exception:
        pass

    return base


@app.get("/api/thesis/latest")
def thesis_latest() -> Any:
    """Most recent generated thesis audit record. If none has been
    generated yet the response is ``{thesis: null, empty: true}`` —
    the React hero card shows its empty state. Trigger generation
    via POST /api/thesis/generate.
    """
    try:
        return _CACHE.get_or_compute("thesis_latest", 30.0, _real_thesis_latest)
    except Exception as exc:
        return _provider_error(
            "trade_thesis_audit_log",
            exc,
            hint="Audit log lives at data/trade_theses.jsonl on the App Service.",
        )


@app.get("/api/thesis/latest/fixture")
def thesis_latest_fixture() -> dict[str, Any]:
    return {
        "thesis": _wrap_thesis_audit_record(_FIXTURE_THESIS),
        "empty": False,
        "source": "fixture",
    }


@app.get("/api/calibration")
def calibration_endpoint(limit: int = 200) -> Any:
    """Confidence-calibration stats for the public /track-record page.

    Reads the same audit log the frontend hits at /api/thesis/history,
    bands the rows by stated conviction, and returns per-bucket hit
    rates + a Brier score + a "calibrated/overconfident/underconfident"
    verdict. The frontend renders a 4-bar reliability diagram.
    """
    if limit < 1 or limit > 500:
        return JSONResponse(status_code=422, content={"detail": "limit out of range"})
    try:
        from backend.services.thesis_service import get_thesis_history
        from backend.services.calibration import compute_calibration

        rows = get_thesis_history(limit)
        stats = compute_calibration(rows)
        return stats.to_dict()
    except Exception as exc:
        return _provider_error("calibration", exc)


@app.get("/api/thesis/history")
def thesis_history(limit: int = 30) -> Any:
    if limit < 1 or limit > 200:
        return JSONResponse(status_code=422, content={"detail": "limit out of range"})
    try:
        from backend.services.thesis_service import get_thesis_history

        rows = get_thesis_history(limit)
        return {"theses": rows, "count": len(rows), "source": "audit_log"}
    except Exception as exc:
        return _provider_error("trade_thesis_audit_log", exc)


async def _sse_stream_thesis_real(mode: str, portfolio_usd: int):
    """Bridge backend.services.thesis_service.stream_thesis to SSE frames."""
    from backend.services.thesis_service import stream_thesis

    async for evt in stream_thesis(mode=mode, portfolio_usd=portfolio_usd):
        # stream_thesis yields {"event": "...", "data": {...}}
        ev = evt.get("event") or "delta"
        data = evt.get("data", {})
        yield f"event: {ev}\ndata: {json.dumps(data)}\n\n"


async def _sse_stream_thesis_fixture():
    """Fallback SSE that streams the fixture thesis progressively. Used by
    /api/thesis/generate/fixture."""
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


def _validate_thesis_body(body: dict[str, Any]) -> tuple[str, int] | JSONResponse:
    mode = body.get("mode", "fast")
    if mode not in ("fast", "deep"):
        return JSONResponse(status_code=422, content={"detail": "mode must be 'fast' or 'deep'"})
    portfolio = body.get("portfolio_usd", 100_000)
    if portfolio is not None and (not isinstance(portfolio, (int, float)) or portfolio <= 0):
        return JSONResponse(status_code=422, content={"detail": "portfolio_usd must be positive"})
    return mode, int(portfolio or 100_000)


@app.post("/api/thesis/generate")
async def thesis_generate(req: Request):
    """Stream a freshly-generated trade thesis via SSE.

    Hits Azure OpenAI through trade_thesis.generate_thesis (under the
    hood — wrapped by backend.services.thesis_service.stream_thesis).
    progress / delta / done event protocol is preserved.
    """
    body = await req.json() if req.headers.get("content-length") else {}
    parsed = _validate_thesis_body(body)
    if isinstance(parsed, JSONResponse):
        return parsed
    mode, portfolio = parsed
    return StreamingResponse(
        _sse_stream_thesis_real(mode, portfolio),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/thesis/regenerate")
async def thesis_regenerate(req: Request):
    return await thesis_generate(req)


@app.post("/api/thesis/generate/fixture")
async def thesis_generate_fixture():
    """Debug-only — stream the deterministic fixture thesis."""
    return StreamingResponse(_sse_stream_thesis_fixture(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------


def _real_backtest(params: dict[str, Any]) -> dict[str, Any]:
    """Run the legacy backtest engine and shape into BacktestLiveResponse.

    backend.services.backtest_service.run_backtest is keyword-only.
    Its `_load_spread_df` helper expects `cointegration.build_spread_df`
    which doesn't exist on the legacy module; bypass it by building the
    spread frame ourselves from `providers.pricing.fetch_pricing_daily`
    + `quantitative_models.compute_spread_zscore` and passing it via
    the optional `spread_df` kwarg.
    """
    from backend.services.backtest_service import run_backtest
    import quantitative_models  # type: ignore
    from providers import pricing as pricing_provider  # type: ignore

    p = params or {}
    entry_z = float(p.get("entry_z", 2.0))
    exit_z = float(p.get("exit_z", 0.5))
    lookback_days = int(p.get("lookback_days", 365))
    slippage_per_bbl = float(p.get("slippage_per_bbl", 0.05))
    commission_per_trade = float(p.get("commission_per_trade", 1.0))

    pricing_res = pricing_provider.fetch_pricing_daily()
    spread_df = quantitative_models.compute_spread_zscore(pricing_res.frame)

    return run_backtest(
        entry_z=entry_z,
        exit_z=exit_z,
        lookback_days=lookback_days,
        slippage_per_bbl=slippage_per_bbl,
        commission_per_trade=commission_per_trade,
        spread_df=spread_df,
    )


def _fixture_backtest(body: dict[str, Any]) -> dict[str, Any]:
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


@app.post("/api/backtest")
async def backtest(req: Request) -> Any:
    """Run the real Brent–WTI mean-reversion backtest with user params.

    Cached 5 minutes per parameter set.
    """
    body = await req.json() if req.headers.get("content-length") else {}
    cache_key = f"backtest::{json.dumps(body, sort_keys=True)}"
    try:
        return _CACHE.get_or_compute(
            cache_key, 300.0, lambda: _real_backtest(body)
        )
    except Exception as exc:
        return _provider_error(
            "backtest_engine",
            exc,
            hint="Engine pulls daily Brent/WTI via yfinance; retry in ~30s.",
        )


@app.post("/api/backtest/fixture")
async def backtest_fixture(req: Request) -> dict[str, Any]:
    body = await req.json() if req.headers.get("content-length") else {}
    return _fixture_backtest(body)


# ---------------------------------------------------------------------------
# Positions (Alpaca paper — fixtures until real wire-up)
# ---------------------------------------------------------------------------


def _alpaca_positions() -> dict[str, Any]:
    from backend.services import alpaca_service

    client = alpaca_service.get_client()
    raw = client.get_all_positions()
    rows = [alpaca_service.map_position(p) for p in raw]
    return {"positions": rows, "count": len(rows), "source": "alpaca_paper"}


def _alpaca_account() -> dict[str, Any]:
    from backend.services import alpaca_service

    client = alpaca_service.get_client()
    acct = client.get_account()
    base = alpaca_service.map_account(acct)
    base.update({"currency": "USD", "status": "ACTIVE", "paper": True, "source": "alpaca_paper"})
    return base


def _alpaca_orders(status: str) -> dict[str, Any]:
    from backend.services import alpaca_service

    client = alpaca_service.get_client()
    # alpaca-py: get_orders accepts optional GetOrdersRequest with status filter
    try:
        from alpaca.trading.requests import GetOrdersRequest  # type: ignore
        from alpaca.trading.enums import QueryOrderStatus  # type: ignore

        status_enum = {
            "open": QueryOrderStatus.OPEN,
            "closed": QueryOrderStatus.CLOSED,
            "all": QueryOrderStatus.ALL,
        }.get(status, QueryOrderStatus.OPEN)
        raw = client.get_orders(filter=GetOrdersRequest(status=status_enum))
    except Exception:
        raw = client.get_orders()
    return {
        "orders": [alpaca_service.map_order(o) for o in raw],
        "status": status,
        "source": "alpaca_paper",
    }


@app.get("/api/positions")
def positions() -> Any:
    """Live Alpaca paper positions. Cached 5s — Alpaca itself rate-limits."""
    try:
        return _CACHE.get_or_compute("positions", 5.0, _alpaca_positions)
    except Exception as exc:
        return _provider_error("alpaca", exc, hint="Check ALPACA_API_KEY_ID / ALPACA_API_SECRET app settings.")


@app.get("/api/positions/account")
def positions_account() -> Any:
    """Live Alpaca paper account balances."""
    try:
        return _CACHE.get_or_compute("positions_account", 5.0, _alpaca_account)
    except Exception as exc:
        return _provider_error("alpaca", exc, hint="Check ALPACA_API_KEY_ID / ALPACA_API_SECRET app settings.")


@app.get("/api/positions/orders")
def positions_orders(status: str = "open") -> Any:
    """Live Alpaca order list filtered by status (open/closed/all)."""
    try:
        return _alpaca_orders(status)
    except Exception as exc:
        return _provider_error("alpaca", exc)


@app.post("/api/positions/execute")
async def positions_execute(
    req: Request,
    _origin: None = Depends(require_execute_origin),
    _rate: None = Depends(enforce_execute_rate_limit),
):
    """Place a real paper order via alpaca-py.

    Hard-gate: requires ALPACA_PAPER == 'true' (set in App Service
    settings). Validates the body server-side. Logs every successful
    fill to data/executions.jsonl. The ALPACA_API_SECRET is never in
    a response body — alpaca_service maps every Alpaca object through
    a whitelist.

    Wave 4 hardening (review #14):
      * S-3: `require_execute_origin` rejects browser POSTs from any
        Origin outside the SWA + localhost dev allowlist.
      * S-4: `enforce_execute_rate_limit` is a file-backed dual gate —
        1 req / 2s inner floor + 30 req / 5min outer ceiling. State
        survives container restart (was a per-process bucket before).
    """
    if os.environ.get("ALPACA_PAPER", "").strip().lower() != "true":
        return JSONResponse(
            status_code=403,
            content={"detail": "Execution disabled (ALPACA_PAPER must be 'true')."},
        )
    body = await req.json() if req.headers.get("content-length") else {}
    symbol = str(body.get("symbol", "")).strip()
    qty = body.get("qty")
    side = body.get("side")
    order_type = body.get("type", "market")
    tif = body.get("time_in_force", "day")
    limit_price = body.get("limit_price")
    if not symbol or not isinstance(qty, (int, float)) or qty <= 0 or side not in ("buy", "sell"):
        return JSONResponse(status_code=422, content={"detail": "symbol/qty/side invalid"})
    if order_type not in ("market", "limit") or tif not in ("day", "gtc", "ioc", "fok"):
        return JSONResponse(status_code=422, content={"detail": "type/time_in_force invalid"})
    try:
        from backend.services import alpaca_service
        from alpaca.trading.client import TradingClient  # noqa: F401  (sanity)
        from alpaca.trading.enums import OrderSide, TimeInForce  # type: ignore
        from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest  # type: ignore

        side_enum = OrderSide.BUY if side == "buy" else OrderSide.SELL
        tif_enum = {
            "day": TimeInForce.DAY,
            "gtc": TimeInForce.GTC,
            "ioc": TimeInForce.IOC,
            "fok": TimeInForce.FOK,
        }[tif]
        if order_type == "market":
            req_obj = MarketOrderRequest(symbol=symbol, qty=qty, side=side_enum, time_in_force=tif_enum)
        else:
            if limit_price is None:
                return JSONResponse(status_code=422, content={"detail": "limit_price required for limit orders"})
            req_obj = LimitOrderRequest(
                symbol=symbol, qty=qty, side=side_enum, time_in_force=tif_enum, limit_price=float(limit_price)
            )
        client = alpaca_service.get_client()
        placed = client.submit_order(req_obj)
        mapped = alpaca_service.map_order(placed)
        # Audit log — append-only JSONL.
        try:
            audit_path = os.path.join(os.environ.get("HOME", "/home/site"), "data", "executions.jsonl")
            os.makedirs(os.path.dirname(audit_path), exist_ok=True)
            with open(audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": _utcnow_iso(), **mapped}) + "\n")
        except Exception:
            pass  # don't fail the order if disk write fails
        return mapped
    except Exception as exc:
        return _provider_error("alpaca_execute", exc)


async def _sse_positions_heartbeat():
    """Long-lived SSE stream for positions trade updates.

    Fixture mode has no real Alpaca trade-update websocket to relay,
    so we emit a steady heartbeat (`event: ping` every 15 s). The
    important thing is that we respond with `text/event-stream` and
    never close the channel — that prevents the EventSource MIME-type
    error and the auto-reconnect loop the browser otherwise enters
    when the response is mistakenly served as HTML.
    """
    # Send a comment-only frame immediately so the browser sees a
    # valid SSE stream during the very first paint.
    yield ": connected\n\n"
    while True:
        await asyncio.sleep(15)
        yield f"event: ping\ndata: {json.dumps({'ts': _utcnow_iso()})}\n\n"


@app.get("/api/positions/stream")
async def positions_stream():
    return StreamingResponse(
        _sse_positions_heartbeat(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Data quality — Q1 slice (read-only collator over per-provider state)
# ---------------------------------------------------------------------------
# Q1-DATA-QUALITY-ROUTE


@app.get("/api/data-quality")
def data_quality() -> Any:
    """Per-provider health envelope.

    Returns 200 even when individual providers are red — red is *data*,
    not a transport error. The frontend DataQualityTile renders the
    grid + per-cell tooltip from this body. Endpoint is intentionally
    public for now; auth gate will land alongside the rest of /api in a
    follow-up.
    """
    try:
        from backend.services.data_quality import compute_quality_envelope

        env = compute_quality_envelope()
        return env.model_dump(mode="json")
    except Exception as exc:  # pragma: no cover — collator is pure
        return _provider_error("data_quality", exc)
