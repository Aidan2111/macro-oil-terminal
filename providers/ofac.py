"""US Treasury OFAC SDN list polling + delta computation (issue #81).

Pulls the public SDN CSV daily, snapshots it on disk, and computes the
delta against the prior snapshot bucketed by region keyword. Three
buckets: ``iran``, ``russia``, ``venezuela``. The delta is what feeds
the catalyst-watchlist signal — a burst of >10 entries within 24h on
any single region flips the LLM prompt's catalyst weighting.

Network access is lazy — the puller is only called from the data-
quality compute path, never at module import time. URL is restricted
to the OFAC public hostnames so bandit B310 stays satisfied.
"""

from __future__ import annotations

import csv
import io
import logging
import pathlib
import urllib.request
from datetime import datetime, timezone
from typing import Any, Iterable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Source URL + region keyword maps
# ---------------------------------------------------------------------------

OFAC_SDN_URL = "https://www.treasury.gov/ofac/downloads/sdn.csv"

# Each bucket → list of UPPER-CASE substring tokens. We match on the
# row's program text + name + remarks columns concatenated, so partial
# hits like "IRGC" or "GAZPROM" land cleanly.
_REGION_TOKENS: dict[str, tuple[str, ...]] = {
    "iran": (
        "IRAN",
        "IRGC",
        "NIOC",
        "MAPNA",
        "SEPAH",
    ),
    "russia": (
        "RUSSIA",
        "RUSSIAN",
        "ROSNEFT",
        "LUKOIL",
        "GAZPROM",
        "SBERBANK",
        "VTB",
    ),
    "venezuela": (
        "VENEZUELA",
        "PDVSA",
    ),
}


# ---------------------------------------------------------------------------
# Disk paths
# ---------------------------------------------------------------------------

_DATA_DIR = pathlib.Path("data/ofac")
SDN_PATH = _DATA_DIR / "sdn.csv"
SDN_PREV_PATH = _DATA_DIR / "sdn-prev.csv"


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------


def _http_get(url: str, *, timeout: float = 30.0) -> bytes:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    # Pin the hostname so bandit B310 (custom schemes / file:/) and
    # SSRF surface stay closed.
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Refusing to fetch non-http(s) URL: {url!r}")
    if not parsed.netloc.endswith(".treasury.gov"):
        raise ValueError(f"Refusing OFAC fetch from non-treasury host: {parsed.netloc!r}")
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "macro-oil-terminal/ofac-poll"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310 — host validated above
        return resp.read()


# ---------------------------------------------------------------------------
# Parse + classify
# ---------------------------------------------------------------------------


def _row_text(row: list[str]) -> str:
    """Concatenate every column into a single uppercase haystack."""
    return " | ".join((c or "").upper() for c in row)


def classify_row(row: list[str]) -> set[str]:
    """Return the set of region buckets a row matches (possibly multiple)."""
    text = _row_text(row)
    hits: set[str] = set()
    for region, tokens in _REGION_TOKENS.items():
        if any(tok in text for tok in tokens):
            hits.add(region)
    return hits


def _row_key(row: list[str]) -> str:
    """Stable key for delta computation. The SDN CSV has the SDN ID
    (entity number) in column 0 followed by name, type, etc."""
    if not row:
        return ""
    return str(row[0]).strip()


def parse_sdn_csv(text: str) -> list[list[str]]:
    """Parse the SDN CSV body; return rows. The OFAC CSV is comma-
    separated with no header row."""
    reader = csv.reader(io.StringIO(text))
    return [row for row in reader if row]


def bucket_counts(rows: Iterable[list[str]]) -> dict[str, int]:
    """Count rows per region bucket, deduplicated by SDN ID."""
    seen: dict[str, set[str]] = {region: set() for region in _REGION_TOKENS}
    for row in rows:
        key = _row_key(row)
        if not key:
            continue
        for region in classify_row(row):
            seen[region].add(key)
    return {region: len(s) for region, s in seen.items()}


# ---------------------------------------------------------------------------
# Snapshot + delta
# ---------------------------------------------------------------------------


def _read_snapshot(path: pathlib.Path) -> list[list[str]]:
    if not path.exists():
        return []
    try:
        return parse_sdn_csv(path.read_text(encoding="utf-8", errors="replace"))
    except Exception as exc:
        logger.debug("OFAC: failed to parse snapshot at %s: %r", path, exc)
        return []


def refresh_snapshot(*, http_get_fn=None) -> tuple[list[list[str]], list[list[str]]]:
    """Pull the live SDN CSV; rotate the previous snapshot.

    Returns ``(current_rows, previous_rows)``. Tests can inject a
    mock `http_get_fn` returning a CSV bytestring to bypass the
    network.
    """
    http_get_fn = http_get_fn or _http_get
    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    body = http_get_fn(OFAC_SDN_URL)
    text = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else str(body)

    # Rotate snapshots — current → prev, write new current.
    prev_rows = _read_snapshot(SDN_PATH)  # prior current becomes new "previous"
    if SDN_PATH.exists():
        try:
            SDN_PREV_PATH.write_text(SDN_PATH.read_text(encoding="utf-8", errors="replace"))
        except Exception as exc:
            logger.debug("OFAC: snapshot rotate failed: %r", exc)

    SDN_PATH.write_text(text, encoding="utf-8")
    current_rows = parse_sdn_csv(text)
    return current_rows, prev_rows


def compute_delta() -> dict[str, Any]:
    """Pull the SDN, compute totals + delta vs prior snapshot, bucket
    by region. Return shape:

      {
        snapshot_date: ISO,
        baseline_date: ISO | None,
        totals:           {iran, russia, venezuela},
        delta_vs_baseline: {iran, russia, venezuela},
        recent_additions: [{region, name, programs, sdn_id}, ...],
        burst_alerts:     [region, ...]   # regions where delta > 10
      }
    """
    current_rows, prev_rows = refresh_snapshot()

    cur_counts = bucket_counts(current_rows)
    prev_counts = bucket_counts(prev_rows)

    delta = {region: cur_counts.get(region, 0) - prev_counts.get(region, 0)
             for region in _REGION_TOKENS}
    burst = [r for r, d in delta.items() if d > 10]

    # Diff entries: rows present in current but not prev.
    prev_keys = {_row_key(r) for r in prev_rows}
    additions: list[dict[str, Any]] = []
    for row in current_rows:
        key = _row_key(row)
        if not key or key in prev_keys:
            continue
        regions = classify_row(row)
        if not regions:
            continue
        # Column layout per OFAC SDN CSV docs:
        #   0: SDN ID  1: Name  2: Type  3: Programs  4: Remarks ...
        name = row[1] if len(row) > 1 else ""
        programs = row[3] if len(row) > 3 else ""
        for region in sorted(regions):
            additions.append(
                {
                    "region": region,
                    "name": name,
                    "programs": programs,
                    "sdn_id": key,
                }
            )

    return {
        "snapshot_date": datetime.now(timezone.utc).isoformat(),
        "baseline_date": (
            datetime.fromtimestamp(SDN_PREV_PATH.stat().st_mtime, timezone.utc).isoformat()
            if SDN_PREV_PATH.exists() else None
        ),
        "totals": cur_counts,
        "delta_vs_baseline": delta,
        "recent_additions": additions[:50],  # cap so the API stays small
        "burst_alerts": burst,
    }
