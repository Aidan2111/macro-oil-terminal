"""Diagnose SWA client-side exception.

Loads each route, captures pageerror / console / requestfailed events,
prints structured JSON, screenshots full-page.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

SWA = "https://delightful-pebble-00d8eb30f.7.azurestaticapps.net"
PAGES = ["/", "/macro/", "/fleet/", "/positions/", "/track-record/"]
SHOTS = Path("/tmp/swa_diag")
SHOTS.mkdir(exist_ok=True)


def main() -> int:
    report = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        for path in PAGES:
            url = SWA + path
            slug = path.strip("/").replace("/", "_") or "home"
            page = ctx.new_page()
            errors: list[dict] = []
            page.on("pageerror", lambda e, errors=errors: errors.append({"kind": "pageerror", "msg": str(e), "stack": getattr(e, "stack", None)}))
            page.on("console", lambda m, errors=errors: errors.append({"kind": f"console.{m.type}", "text": m.text}) if m.type in ("error", "warning") else None)
            page.on("requestfailed", lambda r, errors=errors: errors.append({"kind": "reqfail", "url": r.url, "failure": str(r.failure)}))
            page.on("response", lambda r, errors=errors: errors.append({"kind": "resp_non2xx", "url": r.url, "status": r.status}) if r.status >= 400 else None)
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(4000)
                status = resp.status if resp else 0
                title = page.title()
                body_text = page.inner_text("body")[:500]
                html_len = len(page.content())
            except Exception as exc:
                status = 0
                title = ""
                body_text = ""
                html_len = 0
                errors.append({"kind": "goto_exc", "msg": repr(exc)})
            shot = SHOTS / f"{slug}.png"
            try:
                page.screenshot(path=str(shot), full_page=True)
            except Exception:
                pass
            report[path] = {
                "url": url,
                "status": status,
                "title": title,
                "body_head": body_text,
                "html_len": html_len,
                "errors": errors[:30],
                "screenshot": str(shot),
            }
            page.close()
        browser.close()
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
