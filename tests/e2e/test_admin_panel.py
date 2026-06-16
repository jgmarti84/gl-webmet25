# tests/e2e/test_admin_panel.py
"""
End-to-end tests for the admin panel (served at /admin behind Basic Auth).

Covers, per the e2e rules: page loads, key elements visible, user
interaction (filtering, sorting, the colormap creator), and API integration
(rows populated from /api/v1/admin/*).

Requires the full stack running + a v2 frontend. See docs/E2E_TESTING.md.
"""
import os

from playwright.sync_api import Page, expect

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://frontend-v2:80")


def _open_radars(page: Page):
    page.goto(f"{FRONTEND_URL}/admin", wait_until="networkidle")
    page.click('a[data-section="radars"]')
    page.wait_for_selector("table tbody tr")


# ---------------------------------------------------------------------------
# Page loads + key elements
# ---------------------------------------------------------------------------
def test_admin_page_loads(page: Page, js_errors):
    """The admin SPA loads, shows the sidebar, and logs no JS errors."""
    page.goto(f"{FRONTEND_URL}/admin", wait_until="networkidle")
    expect(page.locator(".sidebar")).to_be_visible()
    expect(page.locator('#sidebar-nav a[data-section="radars"]')).to_be_visible()
    assert not js_errors, f"JS errors on admin load: {js_errors}"


def test_admin_logo_renders(page: Page):
    """The OHMC logo in the sidebar actually loads (naturalWidth > 0)."""
    page.goto(f"{FRONTEND_URL}/admin", wait_until="networkidle")
    loaded = page.evaluate(
        "() => { const i = document.querySelector('.sidebar-logo');"
        " return !!i && i.complete && i.naturalWidth > 0; }"
    )
    assert loaded, "sidebar OHMC logo did not load"


def test_back_to_map_button_present(page: Page):
    """A 'back to map' control is present in the admin header/sidebar."""
    page.goto(f"{FRONTEND_URL}/admin", wait_until="networkidle")
    expect(page.locator("#back-to-map")).to_be_visible()
    expect(page.locator("#sidebar-back-map")).to_be_visible()


# ---------------------------------------------------------------------------
# API integration — tables populated from the admin API
# ---------------------------------------------------------------------------
def test_radars_table_populated_from_api(page: Page):
    """The radars table renders at least one row sourced from the admin API."""
    _open_radars(page)
    assert page.locator("table tbody tr").count() > 0


# ---------------------------------------------------------------------------
# Filtering (Django-admin style) — per-column facets + global search
# ---------------------------------------------------------------------------
def test_radars_have_per_column_filters_and_search(page: Page):
    """Every table exposes a global search + per-column facet controls."""
    _open_radars(page)
    assert page.locator(".filter-bar [data-filter-search]").count() == 1
    assert page.locator(".filter-bar [data-filter-facet]").count() >= 3


def test_text_filter_hides_non_matching_rows(page: Page):
    """Typing a no-match value into a column filter hides all rows."""
    _open_radars(page)
    page.fill('.filter-bar [data-filter-facet="code"]', "zzzz-no-match")
    page.wait_for_timeout(200)
    assert page.locator("table tbody tr:not([hidden])").count() == 0
    # Clearing the filter brings rows back.
    page.fill('.filter-bar [data-filter-facet="code"]', "")
    page.wait_for_timeout(150)
    assert page.locator("table tbody tr:not([hidden])").count() > 0


# ---------------------------------------------------------------------------
# Sorting — all meaningful columns sortable, indicator on click
# ---------------------------------------------------------------------------
def test_columns_are_sortable_with_indicator(page: Page):
    """Multiple columns are sortable; clicking a header shows a ▲/▼ indicator."""
    _open_radars(page)
    assert page.locator("thead [data-sort]").count() >= 5
    page.click('thead [data-sort="title"]')
    page.wait_for_timeout(100)
    indicator = page.locator('thead [data-sort="title"] .sort-ind').inner_text().strip()
    assert indicator in ("▲", "▼"), f"expected sort arrow, got {indicator!r}"


# ---------------------------------------------------------------------------
# Row actions render as icons (pencil / trash), not text
# ---------------------------------------------------------------------------
def test_row_actions_are_icons(page: Page):
    """Edit/Delete row actions render as inline SVG icons."""
    _open_radars(page)
    assert page.locator("tbody [data-edit-radar] svg.ico").count() > 0
    assert page.locator("tbody [data-delete-radar] svg.ico").count() > 0


# ---------------------------------------------------------------------------
# Colormap creator — gradient preview, draggable ticks, Cerrar label
# ---------------------------------------------------------------------------
def _open_creator(page: Page):
    page.goto(f"{FRONTEND_URL}/admin#colormaps", wait_until="networkidle")
    page.wait_for_selector("#cmap-creator-open")
    page.click("#cmap-creator-open")
    page.wait_for_selector("#creator-modal:not(.hidden)")


def test_colormap_creator_opens_and_draws_gradient(page: Page):
    """Opening the creator draws a non-empty gradient on the preview canvas."""
    _open_creator(page)
    drawn = page.evaluate(
        "() => { const c = document.getElementById('creator-canvas');"
        " const d = c.getContext('2d').getImageData(0,0,c.width,1).data;"
        " for (let i=3;i<d.length;i+=4) if (d[i]!==0) return true; return false; }"
    )
    assert drawn, "creator gradient canvas appears empty"
    assert page.locator("#creator-stop-ticks .creator-stop-tick").count() == 2


def test_colormap_creator_close_button_label(page: Page):
    """The creator close button is labeled 'Cerrar'."""
    _open_creator(page)
    assert page.locator("#close-creator-modal").inner_text().strip() == "Cerrar"


def test_colormap_creator_tick_is_draggable(page: Page):
    """Dragging a stop tick over the preview changes its position."""
    _open_creator(page)
    tick = page.locator("#creator-stop-ticks .creator-stop-tick").first
    before = tick.get_attribute("style")
    wrap = page.locator(".creator-preview-wrap").bounding_box()
    box = tick.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(wrap["x"] + wrap["width"] * 0.4, box["y"] + box["height"] / 2, steps=8)
    page.mouse.up()
    page.wait_for_timeout(150)
    after = page.locator("#creator-stop-ticks .creator-stop-tick").first.get_attribute("style")
    assert before != after, "dragging the tick did not change its position"
