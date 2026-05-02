"""AIS multi-stream merger (issue #107).

AISStream went silent for 4 days. One AIS provider is one point of
failure for every Hormuz / Iran / Russia signal in the system. This
module is the pure dedup-by-MMSI core that lets `fleet_service`
fold a secondary AIS feed into the primary's buffer once a paid
secondary subscription (fleetmon / hifleet / Spire) is provisioned.

The merger is intentionally provider-agnostic:

  * Caller supplies the per-source vessel lists already shaped to the
    canonical schema (MMSI / Vessel_Name / Cargo_Volume_bbls /
    Destination / Flag_State / Latitude / Longitude / _ingested_at /
    optional _source).
  * Output is a deduped list keyed by MMSI. When two sources report
    the same vessel, the entry with the **freshest** ``_ingested_at``
    wins; ties broken by source-precedence order.

Pluggable secondary subscription is configured by:

  * ``AIS_SECONDARY_ENABLED=1`` — turn on the merge path.
  * ``AIS_SECONDARY_PROVIDER`` — provider tag (e.g. "fleetmon",
    "hifleet"). Stored on `_source` for audit.

When disabled (default), :func:`merge_vessel_buffers` with a single
input is a passthrough — the deploy works identically to today.
"""

from __future__ import annotations

import os
from typing import Any, Iterable


def is_secondary_enabled() -> bool:
    """Has the operator turned on the secondary merge path?"""
    return os.environ.get("AIS_SECONDARY_ENABLED", "").strip() in (
        "1", "true", "True", "TRUE", "yes", "on",
    )


def secondary_provider_tag() -> str | None:
    """Name of the provisioned secondary feed (audit trail / DQ tile)."""
    return os.environ.get("AIS_SECONDARY_PROVIDER") or None


def _ingested_at(vessel: dict[str, Any]) -> float:
    """Best-effort timestamp accessor; treat missing as oldest."""
    ts = vessel.get("_ingested_at")
    try:
        return float(ts) if ts is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def merge_vessel_buffers(
    *buffers: Iterable[dict[str, Any]],
    source_tags: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    """Merge any number of vessel buffers into a single deduped list.

    Dedup key: MMSI (vessels without one are dropped — the upstream
    schema requires it). When the same MMSI appears in multiple
    buffers, the entry with the freshest ``_ingested_at`` wins.
    Ties are broken by buffer order (earlier buffers take precedence).

    Each output vessel is annotated with ``_source`` from
    ``source_tags`` (positional alignment with ``buffers``); if no
    tags are supplied the input ``_source`` is preserved or set to
    "unknown".

    Empty input → empty list. A single non-empty buffer is returned
    unchanged (cheap fast path so the no-secondary deploy doesn't
    pay any extra cost).
    """
    tags = list(source_tags) if source_tags else []
    while len(tags) < len(buffers):
        tags.append("unknown")

    # Fast path: no secondary feed -> single buffer passthrough.
    materialized = [list(buf) for buf in buffers]
    if len(materialized) == 1:
        out = []
        for v in materialized[0]:
            if v.get("MMSI") is None:
                continue
            if "_source" not in v:
                v = {**v, "_source": tags[0]}
            out.append(v)
        return out

    best_by_mmsi: dict[Any, tuple[int, dict[str, Any]]] = {}
    for buffer_idx, buf in enumerate(materialized):
        for vessel in buf:
            mmsi = vessel.get("MMSI")
            if mmsi is None:
                continue
            tagged = (
                vessel if "_source" in vessel else {**vessel, "_source": tags[buffer_idx]}
            )
            cur = best_by_mmsi.get(mmsi)
            if cur is None:
                best_by_mmsi[mmsi] = (buffer_idx, tagged)
                continue
            cur_idx, cur_v = cur
            if _ingested_at(tagged) > _ingested_at(cur_v):
                best_by_mmsi[mmsi] = (buffer_idx, tagged)
            elif _ingested_at(tagged) == _ingested_at(cur_v) and buffer_idx < cur_idx:
                best_by_mmsi[mmsi] = (buffer_idx, tagged)

    return [entry[1] for entry in best_by_mmsi.values()]


def merge_stats(merged: list[dict[str, Any]]) -> dict[str, int]:
    """Per-source vessel count for /api/data-quality. Useful for
    surfacing "AISStream: 612 / fleetmon: 88" on the tile."""
    stats: dict[str, int] = {}
    for v in merged:
        src = str(v.get("_source") or "unknown")
        stats[src] = stats.get(src, 0) + 1
    return stats


__all__ = [
    "is_secondary_enabled",
    "secondary_provider_tag",
    "merge_vessel_buffers",
    "merge_stats",
]
