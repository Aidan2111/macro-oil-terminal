"""Measure Time-To-Interactive-ish metrics for the Streamlit app.

Captures:
  - domContentLoadedEventEnd - navigationStart (TTI-ish)
  - First paint (performance.getEntriesByType("paint")[0].startTime)
  - document.readyState timing
  - Total render time to [data-testid="hero-band"] visible

Usage:
    python .agent-scripts/measure_tti.py <URL> [--cold] [--runs N] [--out PATH]

--cold   discards storage + cache (fresh browser context per run)
--runs N repeats N times and keeps the median row (default 1)
--out    JSON file to append result to (one JSON line per invocation)
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
import time
from typing import Any

from playwright.sync_api import sync_playwright


def _measure_once(pw, url: str, cold: bool) -> dict[str, Any]:
    browser = pw.chromium.launch(headless=True)
    ctx_kwargs: dict[str, Any] = {"viewport": {"width": 1440, "height": 1800}}
    # Fresh context = no shared storage/cache. Playwright default contexts are
    # already isolated, but we also bypass HTTP cache for cold runs.
    ctx = browser.new_context(**ctx_kwargs)
    if cold:
        # Force no-cache on every request
        def _bypass_cache(route):
            headers = dict(route.request.headers)
            headers["Cache-Control"] = "no-cache, no-store, max-age=0"
            headers["Pragma"] = "no-cache"
            route.continue_(headers=headers)

        ctx.route("**/*", _bypass_cache)

    page = ctx.new_page()

    t0 = time.perf_counter()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=120_000)
    except Exception as exc:
        browser.close()
        return {"url": url, "cold": cold, "error": f"goto: {exc!r}"}

    t_dcl = time.perf_counter() - t0

    # Hero-band visibility (Streamlit renders over websocket, so this is the
    # real "app is alive" signal).
    hero_visible_s: float | None = None
    try:
        page.locator('[data-testid="hero-band"]').first.wait_for(
            state="visible", timeout=120_000
        )
        hero_visible_s = time.perf_counter() - t0
    except Exception:
        hero_visible_s = None

    # Pull browser-native navigation + paint timing
    try:
        raw = page.evaluate(
            """() => {
              const nav = performance.getEntriesByType('navigation')[0] || {};
              const paints = performance.getEntriesByType('paint') || [];
              const first_paint = paints.find(p => p.name === 'first-paint');
              const fcp = paints.find(p => p.name === 'first-contentful-paint');
              return JSON.stringify({
                dom_content_loaded_ms: nav.domContentLoadedEventEnd ?? null,
                load_event_ms: nav.loadEventEnd ?? null,
                dom_interactive_ms: nav.domInteractive ?? null,
                response_end_ms: nav.responseEnd ?? null,
                ready_state: document.readyState,
                first_paint_ms: first_paint ? first_paint.startTime : null,
                first_contentful_paint_ms: fcp ? fcp.startTime : null,
                transfer_size: nav.transferSize ?? null,
                encoded_body_size: nav.encodedBodySize ?? null,
              });
            }"""
        )
        nav = json.loads(raw) if raw else {}
    except Exception as exc:
        nav = {"eval_error": repr(exc)}

    browser.close()

    return {
        "url": url,
        "cold": cold,
        "wall_dom_content_loaded_s": round(t_dcl, 3),
        "wall_hero_visible_s": round(hero_visible_s, 3) if hero_visible_s else None,
        "first_paint_ms": nav.get("first_paint_ms"),
        "first_contentful_paint_ms": nav.get("first_contentful_paint_ms"),
        "dom_content_loaded_ms": nav.get("dom_content_loaded_ms"),
        "dom_interactive_ms": nav.get("dom_interactive_ms"),
        "load_event_ms": nav.get("load_event_ms"),
        "response_end_ms": nav.get("response_end_ms"),
        "ready_state": nav.get("ready_state"),
        "transfer_size": nav.get("transfer_size"),
    }


def _median_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Pick the row whose wall_hero_visible_s is the median."""
    good = [r for r in rows if r.get("wall_hero_visible_s") is not None]
    if not good:
        return rows[0]
    ordered = sorted(good, key=lambda r: r["wall_hero_visible_s"])
    return ordered[len(ordered) // 2]


def main() -> int:
    ap = argparse.ArgumentParser(description="Measure Streamlit TTI metrics.")
    ap.add_argument("url", help="URL to measure")
    ap.add_argument("--cold", action="store_true", help="force cache-bypass")
    ap.add_argument("--runs", type=int, default=1, help="number of runs (keeps median)")
    ap.add_argument("--out", type=str, default=None, help="append JSONL to this path")
    args = ap.parse_args()

    rows: list[dict[str, Any]] = []
    with sync_playwright() as pw:
        for i in range(args.runs):
            row = _measure_once(pw, args.url, cold=args.cold)
            row["run_index"] = i
            rows.append(row)
            print(json.dumps(row), flush=True)

    summary = _median_row(rows) if args.runs > 1 else rows[0]
    summary["timestamp_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    summary["runs"] = args.runs
    if args.runs > 1:
        hero_vals = [r["wall_hero_visible_s"] for r in rows if r.get("wall_hero_visible_s") is not None]
        if hero_vals:
            summary["wall_hero_visible_s_min"] = round(min(hero_vals), 3)
            summary["wall_hero_visible_s_max"] = round(max(hero_vals), 3)
            summary["wall_hero_visible_s_median"] = round(statistics.median(hero_vals), 3)

    # Human-readable summary
    print("--- summary ---", flush=True)
    print(f"URL: {summary['url']}", flush=True)
    print(f"Cold: {summary.get('cold')}  Runs: {summary.get('runs')}", flush=True)
    print(f"Wall DOMContentLoaded: {summary.get('wall_dom_content_loaded_s')} s", flush=True)
    print(f"Wall hero-band visible: {summary.get('wall_hero_visible_s')} s", flush=True)
    print(f"First paint: {summary.get('first_paint_ms')} ms", flush=True)
    print(f"First contentful paint: {summary.get('first_contentful_paint_ms')} ms", flush=True)
    print(f"DOM interactive: {summary.get('dom_interactive_ms')} ms", flush=True)
    print(f"Load event: {summary.get('load_event_ms')} ms", flush=True)
    print(f"Ready state: {summary.get('ready_state')}", flush=True)

    if args.out:
        out = pathlib.Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("a") as fh:
            fh.write(json.dumps(summary) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
