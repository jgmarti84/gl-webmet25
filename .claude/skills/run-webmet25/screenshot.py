#!/usr/bin/env python3
"""
screenshot.py — drive the running WebMet25 frontend with headless Chromium
and capture screenshots of the main map, the admin panel, and the colormap
creator. Also prints a tiny smoke summary (radar count, time-wheel items).

Designed to run INSIDE the `radar_tests` container, which already has
Playwright + Chromium + OS libs baked in (see tests/Dockerfile). From the
repo root:

    docker cp .claude/skills/run-webmet25/screenshot.py radar_tests:/tmp/screenshot.py
    docker exec radar_tests python /tmp/screenshot.py
    docker cp radar_tests:/tmp/webmet-shots ./webmet-shots   # pull PNGs out

Env (devcontainer defaults shown):
    FRONTEND_URL    http://frontend-v2:80
    ADMIN_USERNAME  admin
    ADMIN_PASSWORD  change-me
    OUT_DIR         /tmp/webmet-shots
"""
import os
from pathlib import Path

from playwright.sync_api import sync_playwright

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend-v2:80")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me")
OUT_DIR = Path(os.getenv("OUT_DIR", "/tmp/webmet-shots"))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(
            viewport={"width": 1366, "height": 850},
            http_credentials={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        )
        page = ctx.new_page()

        # 1) Main map
        page.goto(f"{FRONTEND_URL}/", wait_until="networkidle")
        page.wait_for_selector("#radar-list .radar-checkbox-item", state="attached")
        page.wait_for_timeout(800)
        radar_count = page.locator("#radar-list .radar-checkbox-item").count()
        page.screenshot(path=str(OUT_DIR / "webmet-map.png"))

        # 1b) Custom time range → the iOS time wheel
        page.click("#btn-module-c")
        page.click("#btn-custom-range")
        page.wait_for_selector("#start-time-wheel .tw-item")
        wheel_items = page.locator("#start-time-wheel .tw-item").count()
        page.screenshot(path=str(OUT_DIR / "webmet-timewheel.png"))

        # 2) Admin panel — radars
        page.goto(f"{FRONTEND_URL}/admin#radars", wait_until="networkidle")
        page.wait_for_selector("table tbody tr")
        page.screenshot(path=str(OUT_DIR / "webmet-admin-radars.png"))

        # 3) Colormap creator
        page.goto(f"{FRONTEND_URL}/admin#colormaps", wait_until="networkidle")
        page.click("#cmap-creator-open")
        page.wait_for_selector("#creator-modal:not(.hidden)")
        page.wait_for_timeout(200)
        page.screenshot(path=str(OUT_DIR / "webmet-colormap-creator.png"))

        browser.close()

    print(f"radar_count={radar_count} time_wheel_items={wheel_items}")
    for png in sorted(OUT_DIR.glob("*.png")):
        print(f"  wrote {png}")


if __name__ == "__main__":
    main()
