"""Capture the live Azure app's page text (to surface Streamlit tracebacks)."""

from __future__ import annotations

import sys
import time

from playwright.sync_api import sync_playwright


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "https://oil-tracker-app-4281.azurewebsites.net"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(viewport={"width": 1600, "height": 2200}).new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=90_000)
        # Wait long enough for Streamlit to run or crash
        time.sleep(45)
        content = page.inner_text("body")
        print(content[:8000])
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
