"""Freshness badges for graceful degradation (issue #108).

The pre-existing data-quality envelope reports each provider's
``status`` (green / amber / red) plus a freshness target. This
module shapes that into a UI-ready badge payload:

  * ``tier``: ``green`` (<SLA), ``amber`` (SLA..2×SLA),
    ``red`` (>2×SLA AND too old to use)
  * ``age_label``: human-readable string ("2h ago", "silent 27 min")
  * ``hide_content``: True only at the red threshold — amber tiles
    keep rendering with the pill so the operator sees stale-but-here
    rather than a binary up/down.

Also surfaces ``stale_providers``: the list of provider names
currently in amber-or-red, so the LLM thesis context can hedge its
conclusions (the issue body's `stale_providers: [...]` field on the
LLM payload).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _age_seconds(last_good_at, *, now: datetime | None = None) -> float | None:
    """Seconds since ``last_good_at`` (UTC). Returns None when never-seen.

    Accepts datetime objects (used by ProviderHealth) or ISO-8601 strings
    (used by the JSON-shaped envelope that comes back from /api/data-quality).
    """
    if last_good_at is None:
        return None
    if isinstance(last_good_at, str):
        try:
            last_good_at = datetime.fromisoformat(last_good_at.replace("Z", "+00:00"))
        except ValueError:
            return None
    if last_good_at.tzinfo is None:
        last_good_at = last_good_at.replace(tzinfo=timezone.utc)
    cur = now or _now_utc()
    return (cur - last_good_at).total_seconds()


def _format_age(seconds: float) -> str:
    """Compact human-readable age. Always picks the largest unit
    that gives a >0 integer."""
    if seconds < 60:
        return f"{int(seconds)}s ago"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"


def _format_silent(seconds: float) -> str:
    """For providers that should be ~live ("AISStream silent 27 min")."""
    if seconds < 60:
        return f"silent {int(seconds)}s"
    if seconds < 3600:
        return f"silent {int(seconds // 60)} min"
    if seconds < 86400:
        return f"silent {int(seconds // 3600)}h"
    return f"silent {int(seconds // 86400)}d"


def compute_badge(
    *, name: str, last_good_at, freshness_target_hours: float,
    status: str | None = None, now: datetime | None = None,
) -> dict:
    """Build a single tile's freshness badge.

    Returns ``{tier, age_label, age_seconds, hide_content,
    threshold_hours, name}``.

    Tier logic:
      * never-seen + status=red → ``red`` + hide_content=True
      * never-seen + status=amber/green → ``amber`` + hide_content=False
      * age <= SLA → ``green``
      * SLA < age <= 2*SLA → ``amber``
      * age > 2*SLA → ``red``
    """
    age_s = _age_seconds(last_good_at, now=now)
    sla_s = float(freshness_target_hours) * 3600.0

    if age_s is None:
        # Never-seen. Critical providers come in as status=red already.
        if status == "red":
            return {
                "name": name,
                "tier": "red",
                "age_label": "never",
                "age_seconds": None,
                "hide_content": True,
                "threshold_hours": float(freshness_target_hours),
            }
        return {
            "name": name,
            "tier": "amber",
            "age_label": "warming up",
            "age_seconds": None,
            "hide_content": False,
            "threshold_hours": float(freshness_target_hours),
        }

    # AISStream and the other "live" feeds get the silent-X label;
    # everything else gets the X-ago label. Heuristic: if the SLA is
    # under 1h the feed is treated as live.
    is_live_feed = sla_s < 3600.0
    age_label = _format_silent(age_s) if is_live_feed else _format_age(age_s)

    if age_s <= sla_s:
        tier = "green"
        hide = False
    elif age_s <= 2.0 * sla_s:
        tier = "amber"
        hide = False
    else:
        tier = "red"
        hide = True

    return {
        "name": name,
        "tier": tier,
        "age_label": age_label,
        "age_seconds": age_s,
        "hide_content": hide,
        "threshold_hours": float(freshness_target_hours),
    }


def compute_badges_from_envelope(
    envelope: dict, *, now: datetime | None = None,
) -> dict:
    """Walk the data-quality envelope (dict shape) and return:

      {
        "badges": [<one per provider>...],
        "stale_providers": [<names with tier in {amber, red}>],
        "any_red": bool,
      }
    """
    badges: list[dict] = []
    stale: list[str] = []
    any_red = False
    for p in (envelope or {}).get("providers", []) or []:
        badge = compute_badge(
            name=p.get("name") or "unknown",
            last_good_at=p.get("last_good_at"),
            freshness_target_hours=float(p.get("freshness_target_hours") or 1.0),
            status=p.get("status"),
            now=now,
        )
        badges.append(badge)
        if badge["tier"] != "green":
            stale.append(badge["name"])
        if badge["tier"] == "red":
            any_red = True
    return {
        "badges": badges,
        "stale_providers": stale,
        "any_red": any_red,
    }


def stale_providers_from_envelope(
    envelope: dict, *, now: datetime | None = None,
) -> list[str]:
    """Convenience wrapper used by the thesis context to surface the
    `stale_providers` field on the LLM prompt — see ThesisContext.
    """
    return compute_badges_from_envelope(envelope, now=now)["stale_providers"]


__all__ = [
    "compute_badge",
    "compute_badges_from_envelope",
    "stale_providers_from_envelope",
]
