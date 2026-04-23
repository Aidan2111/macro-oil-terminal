from pathlib import Path
from playwright.sync_api import sync_playwright
URL = "https://oil-tracker-app-canadaeast-4474.azurewebsites.net"
OUT = Path("/Users/aidanbothost/Documents/macro_oil_terminal/docs/reviews/ux-evidence")

def wait_ready(page):
    for _ in range(40):
        page.wait_for_timeout(1500)
        try:
            if page.locator('button[role="tab"]').count() >= 3:
                break
        except Exception:
            pass
    page.wait_for_timeout(3000)

def scroll_main(page, y):
    page.evaluate(f"document.querySelector('section.stMain').scrollTo(0, {y});")

def main_h(page):
    return page.evaluate("() => { const s=document.querySelector('section.stMain'); return [s.scrollHeight, s.clientHeight]; }")

def run(vp_name, w, h, mobile=False):
    with sync_playwright() as p:
        b = p.chromium.launch()
        kw = {"viewport":{"width":w,"height":h}}
        if mobile:
            kw.update(is_mobile=True, has_touch=True, device_scale_factor=2)
        ctx = b.new_context(**kw)
        page = ctx.new_page()
        page.goto(URL, wait_until="networkidle", timeout=180000)
        wait_ready(page)
        for tab, key in [("Inventory drawdown","inv"), ("Tanker fleet","tank")]:
            # scroll main container down to reveal tabs before clicking
            page.evaluate("document.querySelector('section.stMain').scrollTo(0, 1400);")
            page.wait_for_timeout(1000)
            page.locator(f'button[role="tab"]:has-text("{tab}")').first.click(force=True)
            page.wait_for_timeout(5000)
            sh, ch = main_h(page)
            print(vp_name, tab, "sh", sh, "ch", ch)
            y = 0; i = 0; step = int(ch * 0.85)
            while y < sh and i < 14:
                scroll_main(page, y)
                page.wait_for_timeout(1400)
                page.screenshot(path=str(OUT / f"{vp_name}_{key}D_{i}.png"))
                y += step; i += 1
        b.close()

run("desktop", 1440, 900)
run("iphone13", 375, 812, mobile=True)
print("done")
