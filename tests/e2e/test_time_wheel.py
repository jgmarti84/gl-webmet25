# tests/e2e/test_time_wheel.py
"""
End-to-end test for the iOS-style time wheel in the custom time range.

The wheel (shared/time-wheel.js) is wired only by the v2 frontend, so these
tests require the v2 frontend. See docs/E2E_TESTING.md.
"""
import os

from playwright.sync_api import Page, expect

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend-v2:80")


def _open_custom_range(page: Page):
    page.goto(f"{FRONTEND_URL}/", wait_until="networkidle")
    page.click("#btn-module-c")                 # open the Time Window panel
    page.click("#btn-custom-range")             # reveal the custom range + wheels
    page.wait_for_selector("#start-time-wheel .tw-item")


def test_time_wheels_render(page: Page):
    """Both start and end wheels render 84 items (24 hours + 60 minutes)."""
    _open_custom_range(page)
    assert page.locator("#start-time-wheel .tw-item").count() == 84
    assert page.locator("#end-time-wheel .tw-item").count() == 84


def test_time_wheel_has_two_columns_and_selection_band(page: Page):
    """Each wheel has two scroll columns (hours/minutes) + a selection band."""
    _open_custom_range(page)
    assert page.locator("#start-time-wheel .tw-col").count() == 2
    expect(page.locator("#start-time-wheel .tw-selection")).to_have_count(1)


def test_time_wheel_tap_selects_value(page: Page):
    """Tapping a minute item selects it and drives the canonical input."""
    _open_custom_range(page)
    # Also need a date for the canonical datetime-local to be composed.
    page.fill("#start-date-date", "2026-06-04")
    page.locator('#start-time-wheel .tw-col[data-unit="m"] .tw-item', has_text="30").first.click()
    page.wait_for_timeout(300)
    canonical = page.input_value("#start-date")
    assert canonical.endswith(":30"), f"expected minute 30 in canonical value, got {canonical!r}"
