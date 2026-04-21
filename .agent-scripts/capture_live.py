"""Capture a single screenshot of the deployed Streamlit app on Azure."""

from __future__ import annotations

import pathlib
import sys
import time

from playwright.sync_api import sync_playwright

OUT = pathlib.Path("docs/screenshots/05_azure_live.png")
OUT.parent.mkdir(parents=True, exist_ok=True)


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else "https://oil-tracker-app-4281.azurewebsites.net"
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_context(
            viewport={"width": 1600, "height": 2000}, device_scale_factor=1
        ).new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=90_000)
        # Wait for the app title to appear (Streamlit renders over websocket)
        try:
            page.locator("h1", has_text="Inventory-Adjusted").first.wait_for(
                state="visible", timeout=90_000
            )
        except Exception as exc:
            print(f"title wait timed out: {exc!r}")
        time.sleep(8)  # allow plotly charts + WebGPU hero to settle
        page.screenshot(path=str(OUT), full_page=True)
        print(f"wrote {OUT}")
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
