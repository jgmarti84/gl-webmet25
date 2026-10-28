#!/usr/bin/env python3
"""Verify Wave-3 behaviours (#2 per-field filtered switch, #10 vigilant
single-click + field persistence). Needs sample COG rows (seed_sample_cogs.sql)
so the product dropdown populates. Runs inside radar_tests.

Operates the product dropdown + coverage toggle directly — no radar selection
needed (the dropdown is populated from getProducts() on init, and frame images
don't render without real COG files anyway)."""
import os
from playwright.sync_api import sync_playwright

U = os.getenv("FRONTEND_URL", "http://frontend-v2:80")


def fval(pg):
    return pg.eval_on_selector("#product-select", "e => e.value")


def sw(pg):
    return pg.eval_on_selector(
        "#toggle-show-filtered",
        "e => ({disabled:e.disabled, checked:e.checked, "
        "title:(e.closest('.toggle-switch-wrapper')||e.parentElement).title})",
    )


def pick(pg, value):
    """Set the product select and fire change (avoids select_option visibility)."""
    pg.eval_on_selector(
        "#product-select",
        "(e,v) => { e.value = v; e.dispatchEvent(new Event('change', {bubbles:true})); }",
        value,
    )


def toggle_filtered(pg, checked):
    pg.eval_on_selector(
        "#toggle-show-filtered",
        "(e,c) => { e.checked = c; e.dispatchEvent(new Event('change', {bubbles:true})); }",
        checked,
    )


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_context().new_page()
        pg.goto(f"{U}/", wait_until="networkidle")
        pg.click("#btn-module-b")
        # Let init + any geolocation auto-init settle, then wait for the cd options.
        pg.wait_for_timeout(3000)
        pg.wait_for_function(
            "() => [...document.querySelectorAll('#product-select option')].some(o => o.value === 'COLMAX')",
            timeout=15000,
        )
        print("cd dropdown:", pg.eval_on_selector_all("#product-select option", "els=>els.map(e=>e.value).filter(Boolean)"))

        # --- #2: COLMAX has both variants -> switch ENABLED ---
        pick(pg, "COLMAX"); pg.wait_for_timeout(1500)
        print("COLMAX     -> field=%-8s switch=%s" % (fval(pg), sw(pg)))

        # toggle filtered OFF -> keep field, swap to COLMAXo
        toggle_filtered(pg, False); pg.wait_for_timeout(1500)
        print("toggle OFF -> field=%-8s (expect COLMAXo)" % fval(pg))
        toggle_filtered(pg, True); pg.wait_for_timeout(1500)
        print("toggle ON  -> field=%-8s (expect COLMAX)" % fval(pg))

        # --- #2: KDPo unfiltered-only -> switch DISABLED + tooltip ---
        # KDPo is only in the unfiltered list, so show unfiltered first.
        toggle_filtered(pg, False); pg.wait_for_timeout(1200)
        pick(pg, "KDPo"); pg.wait_for_timeout(1500)
        print("KDPo       -> field=%-8s switch=%s (expect disabled+title)" % (fval(pg), sw(pg)))

        # --- #10: single-click coverage cd->vig, field persistence ---
        # #coverage-toggle is in the (hidden) Settings panel; fire its click via
        # JS so we don't need the panel visible — the handler runs identically.
        clk = lambda: pg.eval_on_selector("#coverage-toggle", "e => e.click()")
        lbl = lambda: pg.eval_on_selector("#coverage-toggle", "e => e.textContent.trim()")
        print("coverage before:", lbl(), "| field=%s (KDPo, base KDP not in vig)" % fval(pg))
        clk(); pg.wait_for_timeout(3000)
        print("after 1 click :", lbl(),
              "| ls=%s" % pg.evaluate("() => localStorage.getItem('webmet25_coverage_mode')"),
              "| field=%s (expect DBZHo = vig default)" % fval(pg))

        pick(pg, "COLMAXo"); pg.wait_for_timeout(1200)
        clk(); pg.wait_for_timeout(3000)
        print("back to cd    :", lbl(),
              "| field=%s (expect COLMAX/COLMAXo, base kept)" % fval(pg))
        b.close()


if __name__ == "__main__":
    main()
