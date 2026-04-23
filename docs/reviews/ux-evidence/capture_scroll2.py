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
    page.evaluate(f"""
        const s = document.querySelector('section.stMain');
        if(s) s.scrollTo(0, {y});
    """)

def main_height(page):
    return page.evaluate("""() => { const s=document.querySelector('section.stMain'); return s?[s.scrollHeight,s.clientHeight]:[0,0]; }""")

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

        # landing scroll captures
        sh, ch = main_height(page)
        print(vp_name, "sh", sh, "ch", ch)
        step = int(ch * 0.85)
        y = 0
        i = 0
        while y < sh and i < 12:
            scroll_main(page, y)
            page.wait_for_timeout(1200)
            page.screenshot(path=str(OUT / f"{vp_name}_scrollA_{i}.png"))
            y += step
            i += 1

        # tab 2 scroll
        try:
            scroll_main(page, 0)
            page.locator('button[role="tab"]:has-text("Inventory drawdown")').first.click()
            page.wait_for_timeout(4500)
            sh2, ch2 = main_height(page)
            print("inv sh", sh2)
            y=0; i=0; step=int(ch2*0.85)
            while y < sh2 and i < 10:
                scroll_main(page, y)
                page.wait_for_timeout(1200)
                page.screenshot(path=str(OUT / f"{vp_name}_invB_{i}.png"))
                y+=step; i+=1
        except Exception as e:
            print("inv", e)

        # tab 3 scroll
        try:
            scroll_main(page, 0)
            page.locator('button[role="tab"]:has-text("Tanker fleet")').first.click()
            page.wait_for_timeout(4500)
            sh3, ch3 = main_height(page)
            print("tanker sh", sh3)
            y=0; i=0; step=int(ch3*0.85)
            while y < sh3 and i < 10:
                scroll_main(page, y)
                page.wait_for_timeout(1200)
                page.screenshot(path=str(OUT / f"{vp_name}_tankerC_{i}.png"))
                y+=step; i+=1
        except Exception as e:
            print("tanker", e)

        b.close()

run("desktop", 1440, 900)
run("iphone13", 375, 812, mobile=True)
print("done")
