"""Cutover verification — every page loads, hits backend, renders content."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

SWA = "https://delightful-pebble-00d8eb30f.7.azurestaticapps.net"
PAGES = ["/", "/macro", "/fleet", "/positions", "/track-record"]
SHOTS = Path("/tmp/cutover_shots")
SHOTS.mkdir(exist_ok=True)


def main() -> int:
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        api_calls: list[str] = []
        page.on("request", lambda r: api_calls.append(r.url) if "oil-tracker-api-canadaeast-0f18" in r.url else None)
        page.on("pageerror", lambda exc: print(f"PAGE ERROR: {exc}"))

        results: list[tuple[str, bool, int, str]] = []
        for path in PAGES:
            url = SWA + path
            print(f"\n=== {url} ===")
            try:
                resp = page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                page.wait_for_timeout(4000)  # let SWR + first SSE frame land
                status = resp.status if resp else 0
            except Exception as exc:
                print(f"  goto failed: {exc!r}")
                results.append((path, False, 0, "goto_failed"))
                continue
            time.sleep(2)
            shot = SHOTS / f"{path.strip('/').replace('/', '_') or 'home'}.png"
            page.screenshot(path=str(shot), full_page=True)
            html_len = len(page.content())
            text = page.inner_text("body")
            has_error = any(
                bad in text
                for bad in ("Traceback", "TypeError", "Error 500", "Application Error", "Cannot read properties of null")
            )
            print(f"  status={status} html_len={html_len} screenshot={shot.name}")
            print(f"  has_error={has_error}")
            print(f"  body_head: {text[:160]!r}")
            results.append((path, status == 200 and not has_error, status, text[:80]))

        print("\n=== api calls captured ===")
        unique = sorted(set(c for c in api_calls))
        for c in unique[:20]:
            print(f"  {c}")
        print(f"  total api calls: {len(api_calls)}")

        b.close()
        ok = all(r[1] for r in results) and len(unique) > 0
        print(f"\nPASS: {ok}")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
