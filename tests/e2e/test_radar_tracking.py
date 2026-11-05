# tests/e2e/test_radar_tracking.py
"""Storm tracking tool of the single-radar view (design doc §15), on the isolated test stack.

The test stack has no tracking service, so /api/tracking answers 502 there: that is the "not deployed" case, for
real. Every other case fakes the tracking API in the browser (page.route). A throwaway radar E2ET (view enabled, no
data) is created through the admin API and deleted at the end.
"""

import json
import os

import pytest
from playwright.sync_api import Page, expect

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend-v2:80")
CODE = "E2ET"
ADMIN_API = f"{FRONTEND_URL}/api/v1/admin"
AVAILABILITY = f"**/api/tracking/radars/{CODE}/availability"
JOBS = f"**/api/tracking/radars/{CODE}/jobs"
POLL = "**/api/tracking/jobs/*"

FRAMES = [
    {
        "timestamp": f"2026-10-20T22:{m:02d}:00Z",
        "gate_passed": True,
        "counts": {"detected": 1, "convective": 1, "tracked": 1, "forecasts": 1},
        "features": {"type": "FeatureCollection", "features": []},
    }
    for m in (31, 40, 49)
]


@pytest.fixture
def admin_page(browser, admin_storage_state):
    """An admin page context and the E2ET radar; both are cleaned up afterwards."""
    context = browser.new_context(storage_state=admin_storage_state, ignore_https_errors=True)
    api = context.request
    api.delete(f"{ADMIN_API}/radars/{CODE}")  # leftover of an interrupted run, if any
    created = api.post(
        f"{ADMIN_API}/radars",
        data={
            "code": CODE,
            "title": "E2E seguimiento",
            "center_lat": -31.4,
            "center_long": -64.2,
            "img_radio": 240,
            "is_active": True,
            "detail_view_enabled": True,
        },
    )
    assert created.status == 201, created.text()
    page = context.new_page()
    yield page
    page.close()
    api.delete(f"{ADMIN_API}/radars/{CODE}")
    context.close()


def _availability(page: Page, count: int, max_last_n: int = 10) -> None:
    page.route(AVAILABILITY, lambda route: route.fulfill(json={
        "radar_code": CODE, "count": count, "min_time": None, "max_time": None, "max_last_n": max_last_n,
    }))


def _fake_jobs(page: Page) -> list:
    """Answer every job at once with FRAMES; returns the list of request bodies, in order."""
    bodies = []

    def submit(route):
        bodies.append(json.loads(route.request.post_data))
        route.fulfill(status=202, json={
            "job_id": f"job{len(bodies)}", "status": "pending", "radar": CODE,
            "start": bodies[-1]["start"], "end": bodies[-1]["end"], "volumes_total": 7,
        })

    def poll(route):
        route.fulfill(json={
            "job_id": route.request.url.rsplit("/", 1)[-1], "status": "done", "radar": CODE,
            "start": "2026-10-20T22:00:00Z", "end": "2026-10-20T23:00:00Z",
            "progress": {"volumes_total": 7, "volumes_done": 7, "fraction": 1.0},
            "created_at": "2026-10-20T23:00:00Z", "config_in_force": {"dbz_threshold": 35, "apply_scale": True},
            "frames": FRAMES,
        })

    page.route(JOBS, submit)
    page.route(POLL, poll)
    return bodies


def _open(page: Page) -> None:
    page.goto(f"{FRONTEND_URL}/radar.html?code={CODE}", wait_until="networkidle")


def _set_window(page: Page) -> None:
    """The radar has no data, so the view never sets its window; set the inputs as the time panel would."""
    page.evaluate("""() => {
        document.getElementById('start-date').value = '2026-10-20T22:00';
        document.getElementById('end-date').value = '2026-10-20T22:49';
    }""")


def test_without_the_tracking_service_there_is_no_button(admin_page):
    """The test stack has no tracking service (502): the view looks exactly as before."""
    _open(admin_page)
    expect(admin_page.locator("#btn-tracking")).to_be_hidden()


def test_a_radar_without_cubes_shows_a_disabled_button(admin_page):
    _availability(admin_page, count=0)
    _open(admin_page)
    button = admin_page.locator("#btn-tracking")
    expect(button).to_be_visible()
    expect(button).to_be_disabled()
    expect(button).to_have_attribute("title", "Sin datos de seguimiento para este radar")


def test_the_panel_offers_n_and_the_forecast_leads(admin_page):
    _availability(admin_page, count=12)
    _open(admin_page)
    admin_page.click("#btn-tracking")
    expect(admin_page.locator("#panel-tracking")).to_be_visible()

    expect(admin_page.locator(".trk-lastn-btn.active")).to_have_text("3")
    leads = admin_page.locator("#trk-leads input[data-lead]")
    expect(leads).to_have_count(7)
    checked = admin_page.locator("#trk-leads input[data-lead]:checked")
    assert [c.get_attribute("data-lead") for c in checked.all()] == ["18", "36", "54"]
    expect(admin_page.locator("#toggle-tracking")).not_to_be_checked()


def test_n_above_the_service_cap_is_disabled(admin_page):
    _availability(admin_page, count=12, max_last_n=5)
    _open(admin_page)
    admin_page.click("#btn-tracking")
    expect(admin_page.locator('.trk-lastn-btn[data-n="10"]')).to_be_disabled()
    expect(admin_page.locator('.trk-lastn-btn[data-n="5"]')).to_be_enabled()


def test_switching_on_tracks_the_last_n_volumes_of_the_window(admin_page):
    _availability(admin_page, count=12)
    bodies = _fake_jobs(admin_page)
    _open(admin_page)
    admin_page.click("#btn-tracking")
    _set_window(admin_page)

    admin_page.locator("label[for='toggle-tracking']").click()
    expect(admin_page.locator("#trk-status")).to_contain_text("Seguimiento sobre 3 volúmenes")
    assert bodies[0]["last_n"] == 3
    # The window inputs hold whole minutes: one minute of slack keeps the newest volume in.
    end_local = admin_page.evaluate("() => new Date('2026-10-20T22:50').toISOString()")
    assert bodies[0]["end"] == end_local
    expect(admin_page.locator("#trk-config-table")).to_contain_text("Umbral de detección (dBZ)")
    expect(admin_page.locator("#btn-tracking")).to_have_class("icon-btn is-on")

    admin_page.click('.trk-lastn-btn[data-n="5"]')
    admin_page.wait_for_function("() => document.querySelector('#trk-status').textContent.includes('Sólo hay 3')")
    assert bodies[-1]["last_n"] == 5


def test_choices_survive_a_reload_and_off_stops_requests(admin_page):
    _availability(admin_page, count=12)
    bodies = _fake_jobs(admin_page)
    _open(admin_page)
    admin_page.click("#btn-tracking")
    _set_window(admin_page)
    admin_page.click('.trk-lastn-btn[data-n="10"]')
    admin_page.locator("#trk-leads input[data-lead='9']").check()
    admin_page.locator("#trk-leads input[data-lead='54']").uncheck()
    admin_page.locator("label[for='toggle-tracking']").click()
    expect(admin_page.locator("#trk-status")).to_contain_text("Seguimiento sobre")

    _open(admin_page)
    admin_page.click("#btn-tracking")
    expect(admin_page.locator(".trk-lastn-btn.active")).to_have_text("10")
    checked = admin_page.locator("#trk-leads input[data-lead]:checked")
    assert [c.get_attribute("data-lead") for c in checked.all()] == ["9", "18", "36"]
    expect(admin_page.locator("#toggle-tracking")).to_be_checked()

    admin_page.locator("label[for='toggle-tracking']").click()
    sent = len(bodies)
    _set_window(admin_page)
    admin_page.click('.trk-lastn-btn[data-n="3"]')
    admin_page.wait_for_timeout(1500)
    assert len(bodies) == sent, "no tracking request while the tool is off"
    assert admin_page.evaluate("() => localStorage.getItem('webmet25_tracking_enabled')") == "0"


def test_settings_apply_only_with_recalcular(admin_page):
    """Edited settings are flagged and used only after "Recalcular seguimiento", never by other re-runs."""
    _availability(admin_page, count=12)
    bodies = _fake_jobs(admin_page)
    _open(admin_page)
    admin_page.click("#btn-tracking")
    expect(admin_page.locator("#trk-param-dbz")).to_be_visible()  # the settings section starts open
    _set_window(admin_page)
    admin_page.locator("label[for='toggle-tracking']").click()
    expect(admin_page.locator("#trk-status")).to_contain_text("Seguimiento sobre")
    apply = admin_page.locator("#btn-trk-apply")
    expect(apply).to_have_text("Recalcular seguimiento")

    admin_page.fill("#trk-param-dbz", "40")
    expect(apply).to_have_text("Recalcular seguimiento (cambios sin aplicar)")

    # Another re-run (here: a different N) keeps the applied settings.
    admin_page.click('.trk-lastn-btn[data-n="5"]')
    admin_page.wait_for_function("() => document.querySelector('#trk-status').textContent.includes('Sólo hay 3')")
    assert bodies[-1]["config"]["dbz_threshold"] == 35
    expect(apply).to_have_text("Recalcular seguimiento (cambios sin aplicar)")

    sent = len(bodies)
    apply.click()
    admin_page.wait_for_function(f"() => document.querySelector('#btn-trk-apply').textContent === 'Recalcular seguimiento'")
    assert len(bodies) == sent + 1
    assert bodies[-1]["config"]["dbz_threshold"] == 40
