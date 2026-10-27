#!/usr/bin/env python3
"""Verify Wave-4 field-menu accordion (#9). Needs seed_sample_cogs.sql.
Runs inside radar_tests."""
import os
from playwright.sync_api import sync_playwright

U = os.getenv("FRONTEND_URL", "http://frontend-v2:80")


def pick(pg, value):
    pg.eval_on_selector("#product-select",
                        "(e,v)=>{e.value=v;e.dispatchEvent(new Event('change',{bubbles:true}));}", value)


def section(pg, sid):
    return pg.eval_on_selector(
        f"#{sid}",
        "e => ({open:e.classList.contains('open'), disabled:e.classList.contains('disabled'), "
        "bodyShown: getComputedStyle(e.querySelector('.field-section-body')).display !== 'none'})",
    )


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_context().new_page()
        pg.goto(f"{U}/", wait_until="networkidle")
        pg.click("#btn-module-b")
        pg.wait_for_timeout(3000)
        pg.wait_for_function(
            "() => [...document.querySelectorAll('#product-select option')].some(o=>o.value==='COLMAX')",
            timeout=15000)

        ids = ["section-tops-cores", "section-colormap", "section-range", "section-smoothing"]
        print("titles:", pg.eval_on_selector_all("#panel-module-b .field-section-title",
                                                  "els=>els.map(e=>e.textContent.trim().split('\\n')[0].trim())"))
        print("default (all collapsed):", {s: section(pg, s) for s in ids})

        # COLMAX -> Tops&Cores available (not disabled)
        pick(pg, "COLMAX"); pg.wait_for_timeout(1200)
        print("COLMAX tops-cores:", section(pg, "section-tops-cores"))

        # expand colormap, then range
        pg.eval_on_selector("#section-colormap .field-section-header", "e=>e.click()")
        pg.eval_on_selector("#section-range .field-section-header", "e=>e.click()")
        pg.wait_for_timeout(300)
        print("after expand colormap+range:",
              {s: section(pg, s)["open"] for s in ["section-colormap", "section-range"]})
        # collapse colormap again
        pg.eval_on_selector("#section-colormap .field-section-header", "e=>e.click()")
        pg.wait_for_timeout(200)
        print("colormap after re-click open=%s" % section(pg, "section-colormap")["open"])

        # DBZH -> Tops&Cores NOT available -> section disabled + cannot expand
        pick(pg, "DBZH"); pg.wait_for_timeout(1200)
        print("DBZH tops-cores (expect disabled):", section(pg, "section-tops-cores"))
        pg.eval_on_selector("#section-tops-cores .field-section-header", "e=>e.click()")
        pg.wait_for_timeout(200)
        print("DBZH tops-cores after click (expect still closed):", section(pg, "section-tops-cores")["open"])

        # screenshot with a couple sections open
        pg.eval_on_selector("#section-range .field-section-header", "e=>e.click()")  # ensure range open
        pg.wait_for_timeout(300)
        pg.screenshot(path="/tmp/webmet-shots/v2-field-accordion.png")
        b.close()


if __name__ == "__main__":
    main()
