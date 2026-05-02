"""Silence detector — issue #99.

The pre-existing /api/data-quality endpoint reports per-provider
freshness, but nothing watches it. AISStream went silent for 4 days
before anyone noticed. This module computes the actionable subset:
any provider whose `last_good_at` exceeds a severity-tiered threshold.

Severity tiers (provider → max-stale before alerting):

    critical    yfinance, eia, audit_log         >  1h
    warning     cftc, alpaca_paper, news_rss,
                ofac                              >  4h
    info        aisstream, hormuz, iran_*,
                russia                            > 24h

Pure read of the existing data-quality envelope — never calls upstream
providers — so it's cheap to poll from the GH Actions watchdog every
15 min.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any


SeverityTier = str  # "critical" | "warning" | "info"


# Tiered thresholds (hours). A provider whose age exceeds the threshold
# in its tier is alerted with that tier's severity.
_TIER_THRESHOLDS: dict[str, tuple[SeverityTier, float]] = {
    "yfinance":         ("critical", 1.0),
    "eia":              ("critical", 1.0),
    "audit_log":        ("critical", 1.0),
    "cftc":             ("warning", 4.0),
    "alpaca_paper":     ("warning", 4.0),
    "news_rss":         ("warning", 4.0),
    "ofac":             ("warning", 4.0),
    "aisstream":        ("info", 24.0),
    "hormuz":           ("info", 24.0),
    "iran_production":  ("info", 24.0),
    "iran_tankers":     ("info", 24.0),
    "russia":           ("info", 24.0),
}


@dataclass
class SilenceAlert:
    """A provider that exceeded its silence-detector threshold."""

    provider: str
    severity: SeverityTier
    age_hours: float
    threshold_hours: float
    message: str


def _age_hours(last_good_at: datetime | None, *, now: datetime | None = None) -> float | None:
    """Hours since ``last_good_at`` (UTC). Returns None when never-seen."""
    if last_good_at is None:
        return None
    cur = now or datetime.now(timezone.utc)
    if last_good_at.tzinfo is None:
        last_good_at = last_good_at.replace(tzinfo=timezone.utc)
    delta = cur - last_good_at
    return delta.total_seconds() / 3600.0


def compute_alerts_from_envelope(
    envelope: dict | Any,
    *,
    now: datetime | None = None,
) -> list[SilenceAlert]:
    """Return the list of providers currently exceeding their tier
    threshold.

    ``envelope`` may be a :class:`DataQualityEnvelope` model or a plain
    dict (so the GH Actions cron can pass parsed-JSON in directly).
    """
    if envelope is None:
        return []
    if hasattr(envelope, "model_dump"):
        envelope = envelope.model_dump(mode="python")

    providers = envelope.get("providers") if isinstance(envelope, dict) else None
    if not providers:
        return []

    alerts: list[SilenceAlert] = []
    for p in providers:
        name = p.get("name") if isinstance(p, dict) else getattr(p, "name", None)
        last_good = p.get("last_good_at") if isinstance(p, dict) else getattr(p, "last_good_at", None)
        # last_good may be an ISO string from JSON; coerce.
        if isinstance(last_good, str):
            try:
                last_good = datetime.fromisoformat(last_good.replace("Z", "+00:00"))
            except ValueError:
                last_good = None

        tier_info = _TIER_THRESHOLDS.get(name)
        if tier_info is None:
            # Unknown provider — skip rather than alert noisily.
            continue
        severity, threshold = tier_info

        age = _age_hours(last_good, now=now)
        if age is None:
            # Never-seen provider — only the "critical" tier flags this
            # as red; warning/info tolerate "still warming up".
            if severity == "critical":
                alerts.append(
                    SilenceAlert(
                        provider=name,
                        severity=severity,
                        age_hours=float("inf"),
                        threshold_hours=threshold,
                        message=f"{name}: no successful fetch since startup",
                    )
                )
            continue

        if age > threshold:
            alerts.append(
                SilenceAlert(
                    provider=name,
                    severity=severity,
                    age_hours=round(age, 2),
                    threshold_hours=threshold,
                    message=f"{name}: stale {age:.1f}h (threshold {threshold:.1f}h, severity={severity})",
                )
            )

    return alerts


def compute_alerts_live(*, now: datetime | None = None) -> list[SilenceAlert]:
    """Build the envelope on-the-fly, then compute alerts. Used by the
    /api/silence-detector/check endpoint."""
    from . import data_quality as _dq

    envelope = _dq.compute_quality_envelope()
    return compute_alerts_from_envelope(envelope, now=now)


def alerts_to_payload(alerts: list[SilenceAlert]) -> dict:
    """Shape alerts as a JSON-friendly dict suitable for the API.

    Output:
        {
          "checked_at": "...UTC ISO...",
          "alert_count": int,
          "highest_severity": "critical" | "warning" | "info" | "none",
          "alerts": [{provider, severity, age_hours, threshold_hours, message}, ...]
        }
    """
    sev_rank = {"critical": 3, "warning": 2, "info": 1}
    if alerts:
        highest = max(alerts, key=lambda a: sev_rank.get(a.severity, 0)).severity
    else:
        highest = "none"
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "alert_count": len(alerts),
        "highest_severity": highest,
        "alerts": [asdict(a) for a in alerts],
    }


__all__ = [
    "SilenceAlert",
    "compute_alerts_from_envelope",
    "compute_alerts_live",
    "alerts_to_payload",
]
