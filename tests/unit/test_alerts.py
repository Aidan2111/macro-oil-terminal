"""Unit tests for the email-alert stub."""

from __future__ import annotations

import os


def test_below_threshold_returns_none():
    from alerts import maybe_send_zscore_alert
    assert maybe_send_zscore_alert(1.2, 3.0, 2.5) is None


def test_breach_preview_when_env_unset(monkeypatch):
    from alerts import maybe_send_zscore_alert
    for k in ("ALERT_SMTP_HOST", "ALERT_SMTP_USER", "ALERT_SMTP_PASS", "ALERT_SMTP_TO"):
        monkeypatch.delenv(k, raising=False)
    out = maybe_send_zscore_alert(3.8, 3.0, 4.2)
    assert out is not None
    assert out.startswith("[would-send]")


def test_breach_negative_z(monkeypatch):
    from alerts import maybe_send_zscore_alert
    out = maybe_send_zscore_alert(-3.4, 3.0, -1.1)
    assert out is not None
