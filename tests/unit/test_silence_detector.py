"""Issue #99 — silence detector unit tests.

Acceptance criteria:
  * Inject a stale provider into the data-quality envelope and assert
    the alert fires with the correct provider name + age + severity.
  * Multiple stale providers all fire.
  * Healthy envelope produces zero alerts.
  * Never-seen "critical" providers fire; never-seen warning/info
    providers do NOT (might still be warming up).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.services.silence_detector import (
    SilenceAlert,
    alerts_to_payload,
    compute_alerts_from_envelope,
)


_NOW = datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc)


def _envelope(providers: list[dict]) -> dict:
    """Helper — build a minimal envelope dict with the given provider rows."""
    return {
        "generated_at": _NOW.isoformat(),
        "overall": "amber",
        "providers": providers,
    }


def _provider(name: str, *, hours_stale: float | None = 0.1, status: str = "green") -> dict:
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
        "freshness_target_hours": 6.0,
    }


# ---------------------------------------------------------------------------
# Acceptance criteria
# ---------------------------------------------------------------------------
def test_critical_provider_stale_2h_fires_alert():
    """yfinance silent for 2h must fire a critical alert."""
    env = _envelope([_provider("yfinance", hours_stale=2.0)])
    alerts = compute_alerts_from_envelope(env, now=_NOW)
    assert len(alerts) == 1
    assert alerts[0].provider == "yfinance"
    assert alerts[0].severity == "critical"
    assert alerts[0].threshold_hours == 1.0
    assert alerts[0].age_hours >= 1.99 and alerts[0].age_hours <= 2.01


def test_warning_provider_stale_5h_fires_warning():
    env = _envelope([_provider("ofac", hours_stale=5.0)])
    alerts = compute_alerts_from_envelope(env, now=_NOW)
    assert len(alerts) == 1
    assert alerts[0].severity == "warning"
    assert alerts[0].threshold_hours == 4.0


def test_info_provider_stale_25h_fires_info():
    env = _envelope([_provider("aisstream", hours_stale=25.0)])
    alerts = compute_alerts_from_envelope(env, now=_NOW)
    assert len(alerts) == 1
    assert alerts[0].severity == "info"
    assert alerts[0].threshold_hours == 24.0


def test_healthy_envelope_no_alerts():
    env = _envelope([
        _provider("yfinance", hours_stale=0.1),
        _provider("eia", hours_stale=2.0),       # within critical threshold? no — eia threshold is 1h
        _provider("aisstream", hours_stale=0.1),
    ])
    # eia is at 2h which exceeds the 1h critical threshold — drop it.
    env = _envelope([
        _provider("yfinance", hours_stale=0.5),
        _provider("eia", hours_stale=0.5),
        _provider("aisstream", hours_stale=0.1),
    ])
    alerts = compute_alerts_from_envelope(env, now=_NOW)
    assert alerts == []


def test_multiple_stale_providers_all_fire():
    env = _envelope([
        _provider("yfinance", hours_stale=2.0),     # critical
        _provider("ofac", hours_stale=5.0),         # warning
        _provider("aisstream", hours_stale=30.0),   # info
        _provider("cftc", hours_stale=0.5),         # healthy — must NOT fire
    ])
    alerts = compute_alerts_from_envelope(env, now=_NOW)
    names = sorted(a.provider for a in alerts)
    assert names == ["aisstream", "ofac", "yfinance"]
    severities = {a.provider: a.severity for a in alerts}
    assert severities == {
        "yfinance": "critical",
        "ofac": "warning",
        "aisstream": "info",
    }


def test_never_seen_critical_provider_fires():
    """A critical provider with last_good_at=None must fire."""
    env = _envelope([_provider("yfinance", hours_stale=None)])
    alerts = compute_alerts_from_envelope(env, now=_NOW)
    assert len(alerts) == 1
    assert alerts[0].provider == "yfinance"
    assert alerts[0].severity == "critical"
    assert alerts[0].age_hours == float("inf")


def test_never_seen_info_provider_does_not_fire():
    """A never-seen aisstream may still be warming up — no alert."""
    env = _envelope([_provider("aisstream", hours_stale=None)])
    alerts = compute_alerts_from_envelope(env, now=_NOW)
    assert alerts == []


def test_unknown_provider_skipped_not_alerted():
    """Provider names not in the tier map are skipped (don't crash)."""
    env = _envelope([_provider("unknown_provider", hours_stale=999.0)])
    alerts = compute_alerts_from_envelope(env, now=_NOW)
    assert alerts == []


# ---------------------------------------------------------------------------
# Payload shape (used by /api/alerts)
# ---------------------------------------------------------------------------
def test_alerts_to_payload_zero_alerts_returns_none_severity():
    payload = alerts_to_payload([])
    assert payload["alert_count"] == 0
    assert payload["highest_severity"] == "none"
    assert payload["alerts"] == []
    assert "checked_at" in payload


def test_alerts_to_payload_promotes_to_highest_severity():
    """A mix of severities reports the highest."""
    alerts = [
        SilenceAlert("aisstream", "info", 25.0, 24.0, "..."),
        SilenceAlert("ofac", "warning", 5.0, 4.0, "..."),
    ]
    payload = alerts_to_payload(alerts)
    assert payload["highest_severity"] == "warning"
    assert payload["alert_count"] == 2

    alerts.append(SilenceAlert("yfinance", "critical", 2.0, 1.0, "..."))
    payload = alerts_to_payload(alerts)
    assert payload["highest_severity"] == "critical"
    assert payload["alert_count"] == 3


def test_payload_alerts_carry_message_with_age_and_threshold():
    alerts = [SilenceAlert("yfinance", "critical", 2.0, 1.0,
                           "yfinance: stale 2.0h (threshold 1.0h, severity=critical)")]
    payload = alerts_to_payload(alerts)
    msg = payload["alerts"][0]["message"]
    assert "stale 2.0h" in msg
    assert "threshold 1.0h" in msg
    assert "severity=critical" in msg
