"""Email alert stub — fires when the Brent-WTI spread Z-score breaches the threshold.

This is defensive by design: no credentials are bundled. It reads
``ALERT_SMTP_HOST``, ``ALERT_SMTP_PORT``, ``ALERT_SMTP_USER``,
``ALERT_SMTP_PASS``, ``ALERT_SMTP_FROM`` and ``ALERT_SMTP_TO`` from
the environment. If any are missing the function returns a
"would-send" preview string instead of attempting SMTP, so the UI can
surface the intent without ever leaking credentials.

Wire it up from app.py like this::

    from alerts import maybe_send_zscore_alert
    status = maybe_send_zscore_alert(latest_z, z_threshold, latest_spread)
    st.caption(status)
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Optional


def _preview(latest_z: float, threshold: float, spread: float) -> str:
    subject, body = _build(latest_z, threshold, spread)
    return (
        "[would-send] " + subject + "\n" + body[:240]
        + ("..." if len(body) > 240 else "")
    )


def _build(latest_z: float, threshold: float, spread: float) -> tuple[str, str]:
    arrow = "+" if latest_z > 0 else ""
    subject = (
        f"[Oil Terminal] Spread Z-score alert: {arrow}{latest_z:.2f}\u03c3"
        f" (|Z| >= {threshold:.1f})"
    )
    body = (
        "Brent-WTI spread Z-score has breached the configured threshold.\n\n"
        f"  Current Z : {latest_z:+.2f} sigma\n"
        f"  Threshold : +/- {threshold:.2f} sigma\n"
        f"  Spread    : ${spread:+.2f}\n\n"
        "This is an automated notification from the Inventory-Adjusted "
        "Spread Arbitrage terminal. Acknowledge by visiting the dashboard.\n"
    )
    return subject, body


def maybe_send_zscore_alert(
    latest_z: float, threshold: float, spread: float
) -> Optional[str]:
    """Return a status string describing what the function did.

    If ``|latest_z| < threshold`` the function returns ``None`` (no alert).
    If the threshold is breached but SMTP env vars aren't set, the
    returned string begins with ``[would-send]``. If SMTP succeeds the
    returned string begins with ``[sent]``. SMTP failures are caught and
    reported as ``[error]``.
    """
    if abs(latest_z) < threshold:
        return None

    host = os.environ.get("ALERT_SMTP_HOST")
    port = int(os.environ.get("ALERT_SMTP_PORT", "587"))
    user = os.environ.get("ALERT_SMTP_USER")
    pw = os.environ.get("ALERT_SMTP_PASS")
    sender = os.environ.get("ALERT_SMTP_FROM", user)
    to = os.environ.get("ALERT_SMTP_TO")

    if not (host and user and pw and to and sender):
        return _preview(latest_z, threshold, spread)

    subject, body = _build(latest_z, threshold, spread)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.set_content(body)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.starttls(context=context)
            smtp.login(user, pw)
            smtp.send_message(msg)
        return f"[sent] {subject} \u2192 {to}"
    except Exception as exc:
        return f"[error] alert failed: {exc!r}"


__all__ = ["maybe_send_zscore_alert"]
