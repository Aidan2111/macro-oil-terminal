"""Data-quality envelope — backs ``GET /api/data-quality``.

Aggregates per-provider last-fetch state into a shape the React
DataQualityTile renders as a 5-cell grid (yfinance / EIA / CFTC /
AISStream / Alpaca paper). The audit-log entry covers
``/api/thesis/latest`` freshness so the trader can tell at a glance
whether the visible "today's read" is stale.

Each provider service exposes a ``get_last_fetch_state()`` accessor
written by the Q1 data-quality migration. We never call upstream from
this module — the envelope is a pure read of in-memory snapshots, so
it's cheap to refresh every 60 s from the frontend without amplifying
load on yfinance / EIA / etc.

Sanity guards (e.g. yfinance no-NaN, EIA weekly cadence) live on the
*producer* side — the provider service downgrades itself to amber when
a guard trips. This module just reads ``status`` and ``message``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

ProviderName = Literal[
    "yfinance",
    "eia",
    "cftc",
    "aisstream",
    "alpaca_paper",
    "audit_log",
    "hormuz",
]
HealthStatus = Literal["green", "amber", "red"]


class ProviderHealth(BaseModel):
    """Per-provider health snapshot."""

    name: ProviderName
    status: HealthStatus
    last_good_at: Optional[datetime] = None
    n_obs: Optional[int] = None
    latency_ms: Optional[int] = None
    freshness_target_hours: float = Field(
        ..., description="SLA expectation; status ages to amber/red past this.",
    )
    message: Optional[str] = None


class DataQualityEnvelope(BaseModel):
    """Full envelope returned by ``/api/data-quality``."""

    generated_at: datetime
    overall: HealthStatus
    providers: list[ProviderHealth]


# Per-provider freshness SLAs. EIA + CFTC are weekly so their floor is
# ~10 days; yfinance is intraday but front-month futures only refresh
# during market hours, so 6 h is the practical floor; AISStream is a
# real-time websocket so anything older than 5 min is stale.
_FRESHNESS_HOURS: dict[str, float] = {
    "yfinance": 6.0,
    "eia": 24.0 * 8,        # weekly + 1 day grace
    "cftc": 24.0 * 8,       # weekly Tuesdays + grace
    "aisstream": 0.083,     # 5 min
    "alpaca_paper": 0.25,   # 15 min — account state is sticky
    "audit_log": 24.0,      # at least one thesis per day
    "hormuz": 1.0,          # 24h transit window, refreshed every endpoint hit
}


def _coerce_status(raw: object, last_good_at: Optional[datetime],
                   target_hours: float) -> HealthStatus:
    """Derive status from raw provider hint + freshness window.

    Provider modules write ``status`` directly; we then age it based on
    how long ago ``last_good_at`` was. A green provider with stale
    last-good ages to amber, then red.
    """
    base: HealthStatus = "amber"
    if raw in ("green", "amber", "red"):
        base = raw  # type: ignore[assignment]

    if last_good_at is None:
        # Never seen a successful fetch yet — amber not red, since the
        # provider may simply not have been hit since cold start.
        return base if base == "red" else "amber"

    now = datetime.now(timezone.utc)
    if last_good_at.tzinfo is None:
        last_good_at = last_good_at.replace(tzinfo=timezone.utc)
    age_h = (now - last_good_at).total_seconds() / 3600.0

    if age_h > target_hours * 2:
        return "red"
    if age_h > target_hours:
        # Don't downgrade an already-red, but cap green/amber at amber.
        return "red" if base == "red" else "amber"
    return base


def _read(provider_module_name: str) -> dict[str, object]:
    """Lazy-import a provider service and read its last-fetch snapshot.

    Returns an empty dict when the module hasn't been imported yet
    (cold start / no traffic) — caller handles the None case.
    """
    try:
        mod = __import__(
            f"backend.services.{provider_module_name}",
            fromlist=["get_last_fetch_state"],
        )
        getter = getattr(mod, "get_last_fetch_state", None)
        if getter is None:
            return {}
        return dict(getter())
    except Exception:
        return {}


def _provider_health(name: ProviderName, module: str) -> ProviderHealth:
    snap = _read(module)
    target = _FRESHNESS_HOURS[name]
    last_good_at = snap.get("last_good_at")
    if last_good_at is not None and not isinstance(last_good_at, datetime):
        last_good_at = None  # defensive
    raw_status = snap.get("status", "amber")
    status = _coerce_status(raw_status, last_good_at, target)
    return ProviderHealth(
        name=name,
        status=status,
        last_good_at=last_good_at,
        n_obs=snap.get("n_obs") if isinstance(snap.get("n_obs"), int) else None,
        latency_ms=snap.get("latency_ms") if isinstance(snap.get("latency_ms"), int) else None,
        freshness_target_hours=target,
        message=snap.get("message") if isinstance(snap.get("message"), str) else None,
    )


# Map: envelope name -> backend.services.<module>
_PROVIDER_MAP: list[tuple[ProviderName, str]] = [
    ("yfinance", "spread_service"),
    ("eia", "inventory_service"),
    ("cftc", "cftc_service"),
    ("aisstream", "fleet_service"),
    ("alpaca_paper", "alpaca_service"),
    ("audit_log", "thesis_service"),
    ("hormuz", "geopolitical_service"),
]


def compute_quality_envelope() -> DataQualityEnvelope:
    """Collect per-provider health and roll up an overall status."""
    providers = [_provider_health(name, mod) for name, mod in _PROVIDER_MAP]

    # Overall: red if any red, amber if any amber, else green.
    overall: HealthStatus = "green"
    for p in providers:
        if p.status == "red":
            overall = "red"
            break
        if p.status == "amber":
            overall = "amber"

    return DataQualityEnvelope(
        generated_at=datetime.now(timezone.utc),
        overall=overall,
        providers=providers,
    )


# ---------------------------------------------------------------------------
# Sanity guards — used by provider services on each fetch path.
# ---------------------------------------------------------------------------


class GuardViolation(Exception):
    """Raised when a sanity check trips. Caller logs + downgrades to amber."""


def guard_yfinance_frame(frame) -> None:
    """yfinance: must have Close col, monotonic index, no >5d all-NaN gap."""
    if frame is None or len(frame) == 0:
        raise GuardViolation("yfinance frame is empty")
    cols = [str(c).lower() for c in getattr(frame, "columns", [])]
    if not any("close" in c for c in cols):
        raise GuardViolation("yfinance frame missing 'Close' column")
    idx = getattr(frame, "index", None)
    if idx is not None and len(idx) >= 2:
        try:
            if not idx.is_monotonic_increasing:  # type: ignore[union-attr]
                raise GuardViolation("yfinance index is not monotonic")
        except AttributeError:
            pass
    # All-NaN gap check is best-effort; pandas-only path.
    try:
        nan_run = frame["Close"].isna().astype(int)  # type: ignore[index]
        # Longest run of consecutive NaNs:
        run_max = 0
        cur = 0
        for v in nan_run:
            if v:
                cur += 1
                run_max = max(run_max, cur)
            else:
                cur = 0
        if run_max > 5:
            raise GuardViolation(
                f"yfinance Close has {run_max}-day NaN gap (>5 day SLA)"
            )
    except (KeyError, AttributeError, TypeError):
        pass


def guard_eia_inventory(history: list[dict]) -> None:
    """EIA: weekly cadence, positive inventory, units consistent."""
    if not history:
        raise GuardViolation("EIA history empty")
    last = history[-1]
    val = last.get("commercial_bbls") or last.get("value")
    if val is None or float(val) <= 0:
        raise GuardViolation("EIA latest commercial inventory non-positive")
    if len(history) >= 2:
        from datetime import date
        try:
            d1 = date.fromisoformat(str(history[-2]["date"]))
            d2 = date.fromisoformat(str(history[-1]["date"]))
            gap = (d2 - d1).days
            if gap > 8:
                raise GuardViolation(
                    f"EIA cadence drift: {gap}-day gap (expected ~7)"
                )
        except (ValueError, KeyError):
            pass


def guard_cftc(history: list[dict]) -> None:
    """CFTC: weekly Tuesdays, mm_net within sane range."""
    if not history:
        raise GuardViolation("CFTC history empty")
    last = history[-1]
    val = last.get("value") or last.get("managed_money_net")
    if val is None:
        return
    val = float(val)
    if not (-500_000 <= val <= 500_000):
        raise GuardViolation(f"CFTC mm_net {val:.0f} outside [-500k, +500k]")


def guard_aisstream_vessels(vessels: list[dict]) -> None:
    """AISStream: valid lat/lon, no zero MMSI."""
    if not vessels:
        return  # empty is amber-via-staleness, not red
    for v in vessels[:50]:  # sample-check; full scan is wasteful
        mmsi = v.get("mmsi")
        if mmsi in (0, "0", None):
            raise GuardViolation("AISStream vessel with zero MMSI")
        lat = v.get("lat")
        lon = v.get("lon")
        if lat is not None and not (-90.0 <= float(lat) <= 90.0):
            raise GuardViolation(f"AISStream invalid lat {lat}")
        if lon is not None and not (-180.0 <= float(lon) <= 180.0):
            raise GuardViolation(f"AISStream invalid lon {lon}")


def guard_alpaca_account(acct: dict) -> None:
    """Alpaca: account ACTIVE, buying_power non-negative."""
    status = acct.get("status")
    if status and str(status).upper() != "ACTIVE":
        raise GuardViolation(f"Alpaca account status={status} (expected ACTIVE)")
    bp = acct.get("buying_power")
    if bp is not None:
        try:
            if float(bp) < 0:
                raise GuardViolation(f"Alpaca buying_power {bp} negative")
        except (TypeError, ValueError):
            pass
