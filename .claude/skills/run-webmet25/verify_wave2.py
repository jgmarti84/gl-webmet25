#!/usr/bin/env python3
"""Ad-hoc verification driver for the Wave-2 visual changes.
Runs inside radar_tests (Playwright+Chromium baked in)."""
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend-v2:80")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me")
OUT = Path(os.getenv("OUT_DIR", "/tmp/webmet-shots"))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": 1366, "height": 850},
            http_credentials={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        )
        page = ctx.new_page()
        page.goto(f"{FRONTEND_URL}/", wait_until="networkidle")
        page.wait_for_selector("#radar-list .radar-checkbox-item", state="attached")
        page.wait_for_timeout(600)

        # --- Basemap options (#3): no OSM, has Oscuro ---
        page.click("#btn-settings")
        page.wait_for_selector("#basemap-select", state="visible")
        opts = page.eval_on_selector_all(
            "#basemap-select option",
            "els => els.map(e => [e.value, e.textContent.trim()])",
        )
        print("BASEMAP_OPTIONS:", opts)

        # Switch to the dark basemap and screenshot the map.
        page.select_option("#basemap-select", "argenmap_oscuro")
        page.wait_for_timeout(1500)
        page.screenshot(path=str(OUT / "v2-basemap-oscuro.png"))

        # --- Field menu (#6, #7, #8) -------------------------------------------
        # NOTE: the seeded test env has no indexed COGs, so /products?vol_nr=…
        # returns 0 and the field rows never populate via the live path. These
        # items are pure presentation (CSS/markup), so we force-reveal the rows
        # and inject representative options to measure layout + the new tooltip.
        page.click("#btn-module-b")
        page.wait_for_selector("#product-select", state="attached")
        # #7: slider attrs come straight from HTML regardless of data
        attrs = page.eval_on_selector(
            "#tops-cores-size",
            "e => ({min:e.min, max:e.max, step:e.step, value:e.value})",
        )
        print("TOPS_CORES_SLIDER:", attrs)
        # Force-reveal hidden rows + inject colormap options for a realistic measure
        page.evaluate(
            """() => {
                ['colormap-group','range-group','tops-cores-toggle-row','tops-cores-size-row']
                  .forEach(id => { const el=document.getElementById(id); if(el) el.style.display='block'; });
                const cm=document.getElementById('colormap-select');
                if(cm){ cm.innerHTML=''; ['viridis','NWSReflectivity','turbo','plasma']
                  .forEach(n=>{const o=document.createElement('option');o.value=n;o.textContent=n;cm.appendChild(o);}); }
            }"""
        )
        page.wait_for_timeout(200)
        panel_w = page.eval_on_selector("#panel-module-b", "e => e.getBoundingClientRect().width")
        cm_w = page.eval_on_selector("#colormap-select", "e => e.getBoundingClientRect().width")
        rin_w = page.eval_on_selector("#vmin-input", "e => e.getBoundingClientRect().width")
        print("WIDTHS: panel=%.0f colormap=%.0f range-input=%.0f" % (panel_w, cm_w, rin_w))
        # #8: tops&cores "?" tooltip exists and its popup shows on hover
        tip = page.query_selector("#tops-cores-toggle-row .filter-info-tip")
        print("TOPS_TOOLTIP_PRESENT:", bool(tip))
        if tip:
            tip.hover()
            page.wait_for_timeout(300)
            popup_disp = page.eval_on_selector(
                "#tops-cores-toggle-row .filter-info-popup", "e => getComputedStyle(e).display")
            popup_txt = page.eval_on_selector(
                "#tops-cores-toggle-row .filter-info-popup", "e => e.textContent.trim().slice(0,60)")
            print("TOPS_TOOLTIP_ON_HOVER: display=%s text=%r" % (popup_disp, popup_txt))
        page.screenshot(path=str(OUT / "v2-field-menu.png"))

        # --- Play/pause geometry (#4): box identical in both states ------------
        # No frames in this env, so play() no-ops; toggle the .playing class
        # directly to prove the SVG-swap keeps the button geometry fixed.
        box_paused = page.eval_on_selector("#btn-play-pause", "e => { const r=e.getBoundingClientRect(); return {w:r.width,h:r.height}; }")
        play_disp = page.eval_on_selector("#btn-play-pause .icon-play", "e => getComputedStyle(e).display")
        page.evaluate("() => document.getElementById('btn-play-pause').classList.add('playing')")
        page.wait_for_timeout(100)
        box_playing = page.eval_on_selector("#btn-play-pause", "e => { const r=e.getBoundingClientRect(); return {w:r.width,h:r.height}; }")
        pause_disp = page.eval_on_selector("#btn-play-pause .icon-pause", "e => getComputedStyle(e).display")
        play_disp_playing = page.eval_on_selector("#btn-play-pause .icon-play", "e => getComputedStyle(e).display")
        print("PLAY_PAUSE: paused_box=%s playing_box=%s | paused(play=%s) playing(play=%s,pause=%s)" % (
            {k: round(v) for k, v in box_paused.items()},
            {k: round(v) for k, v in box_playing.items()},
            play_disp, play_disp_playing, pause_disp,
        ))
        page.screenshot(path=str(OUT / "v2-playbar-playing.png"))

        browser.close()


if __name__ == "__main__":
    main()
