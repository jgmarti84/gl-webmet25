#!/usr/bin/env python3
"""Spot-check public-frontend Spanish localization (#5). Runs inside radar_tests."""
import os
from playwright.sync_api import sync_playwright

U = os.getenv("FRONTEND_URL", "http://frontend-v2:80")


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_context().new_page()
        pg.goto(f"{U}/", wait_until="networkidle")
        pg.wait_for_timeout(1500)
        print("title:", pg.title())
        # icon-bar tooltips
        for bid in ["btn-module-a", "btn-module-b", "btn-module-c", "btn-snapshot", "btn-settings"]:
            print(bid, "->", pg.eval_on_selector(f"#{bid}", "e=>e.title"))
        # animation buttons + live indicator
        for bid in ["btn-first", "btn-prev", "btn-play-pause", "btn-next", "btn-latest", "btn-cog-refresh-now"]:
            print(bid, "->", pg.eval_on_selector(f"#{bid}", "e=>e.title"))
        print("live-indicator:", pg.eval_on_selector("#live-indicator", "e=>e.textContent.trim()"))
        # open settings, check basemap label + section labels
        pg.click("#btn-settings"); pg.wait_for_timeout(400)
        print("settings text sample:", pg.eval_on_selector("#settings-panel", "e=>e.innerText").replace("\n", " | ")[:300])
        pg.screenshot(path="/tmp/webmet-shots/v2-settings-es.png")
        b.close()


if __name__ == "__main__":
    main()
