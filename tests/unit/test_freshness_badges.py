"""Issue #108 — graceful-degradation freshness badges unit tests.

Acceptance:
  * Tile pill carries tier (green / amber / red), human-readable
    age label, and a hide_content flag that's True only at red.
  * stale_providers list surfaces every provider whose tier is amber
    or red — used by the LLM to hedge.
  * Cached data continues to render at amber; only red hides content.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.services.freshness_badges import (
    compute_badge,
    compute_badges_from_envelope,
    stale_providers_from_envelope,
)


_NOW = datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc)


def _provider_row(name: str, *, hours_stale: float | None, status: str = "green",
                  freshness_target_hours: float = 6.0) -> dict:
    if hours_stale is None:
        last_good = None
    else:
        last_good = (_NOW - timedelta(hours=hours_stale)).isoformat()
    return {
        "name": name,
        "status": status,
        "last_good_at": last_good,
        "n_obs": 1,
        "latency_ms": 50,
        "freshness_target_hours": freshness_target_hours,
    }


def _envelope(rows: list[dict]) -> dict:
    return {"generated_at": _NOW.isoformat(), "overall": "green", "providers": rows}


# ---------------------------------------------------------------------------
# Single-provider badge logic
# ---------------------------------------------------------------------------
def test_green_when_age_within_sla():
    row = _provider_row("yfinance", hours_stale=2.0, freshness_target_hours=6.0)
    badge = compute_badge(
        name=row["name"], last_good_at=row["last_good_at"],
        freshness_target_hours=row["freshness_target_hours"], now=_NOW,
    )
    assert badge["tier"] == "green"
    assert badge["hide_content"] is False
    assert "h ago" in badge["age_label"]


def test_amber_when_between_sla_and_2x_sla():
    row = _provider_row("yfinance", hours_stale=8.0, freshness_target_hours=6.0)
    badge = compute_badge(
        name=row["name"], last_good_at=row["last_good_at"],
        freshness_target_hours=row["freshness_target_hours"], now=_NOW,
    )
    assert badge["tier"] == "amber"
    assert badge["hide_content"] is False  # amber keeps rendering


def test_red_when_above_2x_sla_hides_content():
    row = _provider_row("yfinance", hours_stale=15.0, freshness_target_hours=6.0)
    badge = compute_badge(
        name=row["name"], last_good_at=row["last_good_at"],
        freshness_target_hours=row["freshness_target_hours"], now=_NOW,
    )
    assert badge["tier"] == "red"
    assert badge["hide_content"] is True


def test_live_feed_uses_silent_label():
    """SLA < 1h ⇒ live feed ⇒ "silent X min" wording per the issue body."""
    row = _provider_row("aisstream", hours_stale=27.0 / 60.0, freshness_target_hours=0.083)
    badge = compute_badge(
        name=row["name"], last_good_at=row["last_good_at"],
        freshness_target_hours=row["freshness_target_hours"], now=_NOW,
    )
    assert badge["age_label"].startswith("silent ")


def test_never_seen_critical_red_hides_content():
    badge = compute_badge(
        name="yfinance", last_good_at=None, freshness_target_hours=6.0,
        status="red", now=_NOW,
    )
    assert badge["tier"] == "red"
    assert badge["hide_content"] is True
    assert badge["age_label"] == "never"


def test_never_seen_warming_up_amber_keeps_content():
    badge = compute_badge(
        name="aisstream_secondary", last_good_at=None,
        freshness_target_hours=0.083, status="amber", now=_NOW,
    )
    assert badge["tier"] == "amber"
    assert badge["hide_content"] is False
    assert badge["age_label"] == "warming up"


def test_age_label_picks_largest_unit():
    """Below 60s: '<n>s ago'. Below 1h: 'm ago'. Else 'h ago' / 'd ago'."""
    row = _provider_row("daily-feed", hours_stale=0.5, freshness_target_hours=24.0)  # 30 min
    badge = compute_badge(
        name=row["name"], last_good_at=row["last_good_at"],
        freshness_target_hours=row["freshness_target_hours"], now=_NOW,
    )
    assert "m ago" in badge["age_label"]


# ---------------------------------------------------------------------------
# Envelope-level helpers
# ---------------------------------------------------------------------------
def test_compute_badges_from_envelope_returns_full_payload():
    env = _envelope([
        _provider_row("yfinance", hours_stale=2.0, freshness_target_hours=6.0),
        # 7 min stale vs 5 min SLA -> amber (< 2x SLA = 10 min)
        _provider_row("aisstream", hours_stale=7.0 / 60.0, freshness_target_hours=0.083),
        # 30 days stale vs 8-day SLA -> red (>2x SLA)
        _provider_row("eia", hours_stale=24.0 * 30, freshness_target_hours=24.0 * 8),
    ])
    out = compute_badges_from_envelope(env, now=_NOW)
    assert len(out["badges"]) == 3
    tiers = {b["name"]: b["tier"] for b in out["badges"]}
    assert tiers["yfinance"] == "green"
    assert tiers["aisstream"] == "amber"
    assert tiers["eia"] == "red"
    assert sorted(out["stale_providers"]) == ["aisstream", "eia"]
    assert out["any_red"] is True


def test_stale_providers_helper_isolates_amber_and_red():
    env = _envelope([
        _provider_row("yfinance", hours_stale=2.0, freshness_target_hours=6.0),
        _provider_row("ofac", hours_stale=72.0, freshness_target_hours=24.0),
    ])
    stale = stale_providers_from_envelope(env, now=_NOW)
    assert "yfinance" not in stale
    assert "ofac" in stale


def test_empty_envelope_returns_empty_payload():
    out = compute_badges_from_envelope({"providers": []}, now=_NOW)
    assert out == {"badges": [], "stale_providers": [], "any_red": False}


def test_amber_continues_to_render_red_does_not():
    """The whole point of issue #108 — amber pill is informational,
    red pill hides the cached content."""
    env = _envelope([
        _provider_row("amber-feed", hours_stale=8.0, freshness_target_hours=6.0),
        _provider_row("red-feed", hours_stale=20.0, freshness_target_hours=6.0),
    ])
    out = compute_badges_from_envelope(env, now=_NOW)
    badges_by_name = {b["name"]: b for b in out["badges"]}
    assert badges_by_name["amber-feed"]["hide_content"] is False
    assert badges_by_name["red-feed"]["hide_content"] is True
