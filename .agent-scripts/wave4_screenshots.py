"""Wave 4 mobile re-screenshots at 375 / 412 / 768.

Runs the same diagnostics as visual_audit_one.py over three viewports
and the five public routes, saving PNGs and a per-shot diagnostic JSON
under .agent-scripts/wave4-screenshots/.

Usage from the repo root:
    python .agent-scripts/wave4_screenshots.py

The agent's sandboxed network is allowlisted to a tiny set; this
script must be run on the user's host.
"""

from __future__ import annotations

import json
import os
import sys

from playwright.sync_api import sync_playwright


BASE = "https://delightful-pebble-00d8eb30f.7.azurestaticapps.net"
ROUTES = ["/", "/macro/", "/fleet/", "/positions/", "/track-record/"]
VIEWPORTS = [
    ("375", 375, 812),  # iPhone 13 mini
    ("412", 412, 915),  # Pixel 7
    ("768", 768, 1024),  # iPad portrait
]
OUT = os.path.join(os.path.dirname(__file__), "wave4-screenshots")

DIAG_JS = """
() => {
  const dw = document.documentElement.clientWidth;
  const horizScroll = document.documentElement.scrollWidth > dw;
  const tinyTaps = [...document.querySelectorAll('button, a, [role=button], input, select')]
    .filter(el => {
      const r = el.getBoundingClientRect();
      return (r.width < 44 || r.height < 44) && r.width > 0 && r.height > 0;
    })
    .slice(0, 12)
    .map(el => ({
      tag: el.tagName,
      w: Math.round(el.getBoundingClientRect().width),
      h: Math.round(el.getBoundingClientRect().height),
      text: ((el.innerText || el.value || '') + '').slice(0, 30),
    }));
  return {
    horizScroll,
    docWidth: document.documentElement.scrollWidth,
    clientWidth: dw,
    tinyTaps,
  };
}
"""


def slug(path: str) -> str:
    return path.strip("/").replace("/", "_") or "home"


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    summary: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for vname, w, h in VIEWPORTS:
            ctx = browser.new_context(
                viewport={"width": w, "height": h},
                device_scale_factor=2,
                user_agent=(
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
                    "Mobile/15E148 Safari/604.1"
                ),
            )
            page = ctx.new_page()
            for route in ROUTES:
                url = BASE + route
                try:
                    page.goto(url, wait_until="networkidle", timeout=45_000)
                    page.wait_for_timeout(1_500)
                    diag = page.evaluate(DIAG_JS)
                    out_png = os.path.join(OUT, f"{vname}_{slug(route)}.png")
                    page.screenshot(path=out_png, full_page=True)
                    summary.append(
                        {
                            "viewport": vname,
                            "route": route,
                            "horizScroll": diag.get("horizScroll"),
                            "docWidth": diag.get("docWidth"),
                            "clientWidth": diag.get("clientWidth"),
                            "tinyTapsCount": len(diag.get("tinyTaps") or []),
                            "screenshot": os.path.relpath(out_png),
                        }
                    )
                    print(
                        f"  {vname:>3}px {route:<16} horizScroll="
                        f"{diag.get('horizScroll')!s:<5} taps<44px="
                        f"{len(diag.get('tinyTaps') or [])}"
                    )
                except Exception as exc:  # noqa: BLE001
                    print(f"  {vname:>3}px {route:<16} FAILED: {exc}")
                    summary.append(
                        {"viewport": vname, "route": route, "error": str(exc)}
                    )
            ctx.close()
        browser.close()
    with open(os.path.join(OUT, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nWrote {len(summary)} entries to {OUT}/summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
