"""Baseline perf measurement via Playwright + Chrome DevTools.

Captures two passes against the live site:
  - cold (fresh context, no cache)
  - warm (same page reloaded)

Measures: TTFB, time to 'Inventory-Adjusted' title visible, time to
first chart visible, total bytes pulled. Writes a JSON report.
"""

from __future__ import annotations

import json
import pathlib
import sys
import time

from playwright.sync_api import sync_playwright


URL = sys.argv[1] if len(sys.argv) > 1 else "https://oil-tracker-app-4281.azurewebsites.net"
OUT = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else pathlib.Path("docs/perf/baseline.json")
OUT.parent.mkdir(parents=True, exist_ok=True)


def run_pass(pw, label: str, fresh_context: bool):
    browser = pw.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 1800})
    page = ctx.new_page()

    total_bytes = {"count": 0, "headers": 0, "body": 0}
    requests_log: list[dict] = []

    def on_response(r):
        try:
            body_len = 0
            try:
                body_len = len(r.body())
            except Exception:
                pass
            total_bytes["count"] += 1
            total_bytes["body"] += body_len
            requests_log.append({
                "url": r.url[:160],
                "status": r.status,
                "body": body_len,
            })
        except Exception:
            pass

    page.on("response", on_response)

    t0 = time.perf_counter()
    page.goto(URL, wait_until="domcontentloaded", timeout=90_000)
    ttfb_s = time.perf_counter() - t0

    # Time to title (Streamlit over websocket)
    try:
        page.locator("h1", has_text="Inventory-Adjusted").first.wait_for(state="visible", timeout=120_000)
    except Exception:
        pass
    tti_s = time.perf_counter() - t0

    # Time to first chart (SVG or canvas)
    try:
        page.locator("canvas, svg.main-svg").first.wait_for(state="visible", timeout=60_000)
    except Exception:
        pass
    tfirst_chart_s = time.perf_counter() - t0

    total_s = time.perf_counter() - t0

    # Grab perf navigation timing from the page
    nav_timing = page.evaluate(
        "() => JSON.stringify(performance.getEntriesByType('navigation')[0] || {})"
    )

    # Resource count & big items
    resource_timing = page.evaluate("""() => {
      const rs = performance.getEntriesByType('resource');
      return JSON.stringify({
        count: rs.length,
        total_bytes: rs.reduce((s, r) => s + (r.transferSize || 0), 0),
        largest: rs.sort((a, b) => (b.transferSize||0) - (a.transferSize||0)).slice(0, 8).map(r => ({
          name: r.name.slice(-120),
          size: r.transferSize || 0,
          duration_ms: Math.round(r.duration)
        }))
      });
    }""")

    browser.close()

    return {
        "label": label,
        "url": URL,
        "ttfb_s": round(ttfb_s, 3),
        "tti_title_s": round(tti_s, 3),
        "t_first_chart_s": round(tfirst_chart_s, 3),
        "total_s": round(total_s, 3),
        "playwright_response_count": total_bytes["count"],
        "playwright_body_bytes": total_bytes["body"],
        "nav_timing": json.loads(nav_timing) if nav_timing else {},
        "resource_timing": json.loads(resource_timing) if resource_timing else {},
    }


def main() -> int:
    with sync_playwright() as pw:
        cold = run_pass(pw, "cold", fresh_context=True)
        warm = run_pass(pw, "warm", fresh_context=False)
    report = {"url": URL, "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "cold": cold, "warm": warm}
    OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
