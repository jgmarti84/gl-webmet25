# tests/e2e/test_radar_ordering.py
"""
End-to-end test for the radar selection ordering on the main map.

Rule (controls.js -> sortRadarsForDisplay):
  1. active before inactive
  2. RMA group before AR group (other prefixes last)
  3. numeric ascending within a group, with number 0 (RMA00) sorted LAST

Requires the full stack + v2 frontend. See docs/E2E_TESTING.md.
"""
import os
import re

from playwright.sync_api import Page

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend-v2:80")


def _sort_key(code: str, inactive: bool):
    m = re.match(r"^([A-Za-z]+)(\d+)$", code or "")
    prefix = (m.group(1) if m else code).upper()
    num = int(m.group(2)) if m else 10**9
    prefix_order = 0 if prefix == "RMA" else 1 if prefix == "AR" else 2
    num_key = 10**9 if num == 0 else num
    return (1 if inactive else 0, prefix_order, num_key, code)


def _radar_list(page: Page):
    return page.eval_on_selector_all(
        "#radar-list .radar-checkbox-item",
        "items => items.map(it => ({"
        " code: (it.querySelector('label')?.textContent || '').split(' - ')[0].trim(),"
        " inactive: it.classList.contains('radar-inactive') }))",
    )


def test_main_map_loads(page: Page, js_errors):
    """The main map loads and populates the radar list without JS errors."""
    page.goto(f"{FRONTEND_URL}/", wait_until="networkidle")
    page.wait_for_selector("#radar-list .radar-checkbox-item", state="attached")
    assert page.locator("#radar-list .radar-checkbox-item").count() > 0
    assert not js_errors, f"JS errors on main map load: {js_errors}"


def test_radar_list_ordered_per_rule(page: Page):
    """The rendered radar list matches the documented ordering rule."""
    page.goto(f"{FRONTEND_URL}/", wait_until="networkidle")
    page.wait_for_selector("#radar-list .radar-checkbox-item", state="attached")
    page.wait_for_timeout(500)  # let init() finish populating
    items = _radar_list(page)
    actual = [it["code"] for it in items]
    expected = [it["code"] for it in sorted(items, key=lambda it: _sort_key(it["code"], it["inactive"]))]
    assert actual == expected, f"radar order\n  actual={actual}\n  expected={expected}"


def test_admin_link_present_in_settings(page: Page):
    """The main map links to /admin from the settings panel."""
    page.goto(f"{FRONTEND_URL}/", wait_until="networkidle")
    assert page.get_attribute("#admin-link", "href") == "/admin"
