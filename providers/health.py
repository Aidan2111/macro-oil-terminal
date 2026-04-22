"""Aggregated health-check for the provider layer.

Every provider exposes ``health_check() -> {ok, latency_ms, note}``.
This module aggregates them into a sidebar-ready traffic-light panel.
"""

from __future__ import annotations

import os
import time
from typing import Dict, List


def _safe(fn, label: str) -> dict:
    try:
        res = fn() or {}
    except Exception as exc:
        res = {"ok": False, "latency_ms": 0, "note": f"{type(exc).__name__}: {exc}"[:160]}
    res.setdefault("ok", False)
    res.setdefault("latency_ms", 0)
    res.setdefault("note", "")
    res["label"] = label
    return res


def providers_health() -> List[dict]:
    """Return a list of dicts ready for the sidebar rendering."""
    rows: List[dict] = []

    # --- pricing ---
    from . import _yfinance as yfm
    rows.append({**_safe(yfm.health_check, "yfinance (pricing)"), "kind": "pricing"})

    if os.environ.get("TWELVE_DATA_API_KEY") or os.environ.get("TWELVEDATA_API_KEY"):
        from . import _twelvedata as td
        rows.append({**_safe(td.health_check, "Twelve Data (pricing)"), "kind": "pricing"})
    else:
        rows.append({
            "label": "Twelve Data (pricing)", "ok": None, "latency_ms": 0,
            "note": "TWELVE_DATA_API_KEY not set (skipping)", "kind": "pricing",
        })

    if os.environ.get("POLYGON_API_KEY"):
        from . import _polygon as pg
        rows.append({**_safe(pg.health_check, "Polygon.io (pricing)"), "kind": "pricing"})
    else:
        rows.append({
            "label": "Polygon.io (pricing)", "ok": None, "latency_ms": 0,
            "note": "POLYGON_API_KEY not set (skipping)", "kind": "pricing",
        })

    # --- inventory ---
    from . import _eia as eia
    eia_label = "EIA v2 API (inventory)" if os.environ.get("EIA_API_KEY") else "EIA dnav (inventory)"
    rows.append({**_safe(eia.health_check, eia_label), "kind": "inventory"})

    if os.environ.get("FRED_API_KEY"):
        def _fred_ping():
            import requests
            t0 = time.monotonic()
            r = requests.get(
                "https://api.stlouisfed.org/fred/series",
                params={"series_id": "WCESTUS1", "api_key": os.environ["FRED_API_KEY"], "file_type": "json"},
                timeout=6,
            )
            return {"ok": r.status_code == 200, "latency_ms": int((time.monotonic() - t0) * 1000), "note": f"status={r.status_code}"}
        rows.append({**_safe(_fred_ping, "FRED API (inventory fallback)"), "kind": "inventory"})
    else:
        rows.append({
            "label": "FRED API (inventory fallback)", "ok": None, "latency_ms": 0,
            "note": "FRED_API_KEY not set (skipping)", "kind": "inventory",
        })

    # --- AIS ---
    if os.environ.get("AISSTREAM_API_KEY"):
        rows.append({
            "label": "aisstream.io (AIS)", "ok": True, "latency_ms": 0,
            "note": "key present — live mode active", "kind": "ais",
        })
    else:
        rows.append({
            "label": "aisstream.io (AIS)", "ok": None, "latency_ms": 0,
            "note": "AISSTREAM_API_KEY not set (Q3 2024 snapshot)", "kind": "ais",
        })

    # --- CFTC positioning ---
    from . import _cftc
    rows.append({**_safe(_cftc.health_check, "CFTC disaggregated (positioning)"), "kind": "positioning"})

    return rows


__all__ = ["providers_health"]
