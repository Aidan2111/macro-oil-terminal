"""Single-viewport visual audit. Args: <viewport_name> <width> <height>."""

from __future__ import annotations

import json
import os
import sys
from playwright.sync_api import sync_playwright


ROUTES = ["/", "/macro/", "/fleet/", "/positions/", "/track-record/"]
BASE = "https://delightful-pebble-00d8eb30f.7.azurestaticapps.net"
OUT = "/tmp/visual-audit"

DIAG_JS = """
() => {
  const dw = document.documentElement.clientWidth;
  const horizScroll = document.documentElement.scrollWidth > dw;
  const overflowing = [...document.querySelectorAll('*')].filter(el => {
    const r = el.getBoundingClientRect();
    return r.right > dw + 1;
  }).slice(0, 10).map(el => ({
    tag: el.tagName,
    cls: (el.className && el.className.toString && el.className.toString().slice(0, 80)) || '',
    w: Math.round(el.getBoundingClientRect().width),
    right: Math.round(el.getBoundingClientRect().right),
  }));
  const tinyTaps = [...document.querySelectorAll('button, a, [role=button], input, select')].filter(el => {
    const r = el.getBoundingClientRect();
    return (r.width < 44 || r.height < 44) && r.width > 0 && r.height > 0;
  }).slice(0, 12).map(el => ({
    tag: el.tagName,
    cls: (el.className && el.className.toString && el.className.toString().slice(0, 60)) || '',
    w: Math.round(el.getBoundingClientRect().width),
    h: Math.round(el.getBoundingClientRect().height),
    text: ((el.innerText || el.value || '') + '').slice(0, 30),
  }));
  const fontSizes = [...document.querySelectorAll('p, span, div, button, a')]
    .map(el => parseFloat(getComputedStyle(el).fontSize))
    .filter(s => s > 0 && s < 12).length;
  return { dw, horizScroll, overflowing, tinyTaps, tinyFontCount: fontSizes };
}
"""


def main() -> int:
    name = sys.argv[1]
    w = int(sys.argv[2])
    h = int(sys.argv[3])
    os.makedirs(OUT, exist_ok=True)
    findings: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": w, "height": h}, device_scale_factor=2
        )
        for route in ROUTES:
            page = ctx.new_page()
            url = f"{BASE}{route}"
            slug = route.strip("/").replace("/", "-") or "home"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
                page.wait_for_timeout(2500)
                diag = page.evaluate(DIAG_JS)
                page.screenshot(path=f"{OUT}/{name}_{slug}.png", full_page=True)
            except Exception as exc:
                diag = {"error": repr(exc)}
            findings.append({"viewport": name, "route": route, **diag})
            page.close()
        ctx.close()
        browser.close()
    out_path = f"{OUT}/findings_{name}.json"
    with open(out_path, "w") as f:
        json.dump(findings, f, indent=2, default=str)
    print(out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
