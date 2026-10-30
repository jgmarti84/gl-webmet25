# tests/auth/test_permissions.py
"""Per-user permissions to open one-radar detail views (spec C, plan C-1)."""

import pytest
from sqlalchemy.exc import IntegrityError

from api.app.auth import permissions as perms
from api.app.auth.google import GoogleIdentity
from radar_db.models import Permission, Radar

from .conftest import login


@pytest.fixture
def make_radar(test_db_session):
    """Factory for test radars. Codes start with TST so they never clash with real radars."""

    def _make(code="TSTA", detail_view_enabled=True):
        radar = Radar(
            code=code,
            title=f"Test {code}",
            center_lat=-31.4,
            center_long=-64.2,
            img_radio=240,
            detail_view_enabled=detail_view_enabled,
        )
        test_db_session.add(radar)
        test_db_session.flush()
        return radar

    return _make


def _grant(db, user, *resources):
    """Store detail-view permissions for a user, bypassing the service (the thing under test elsewhere)."""
    for resource in resources:
        db.add(Permission(user_id=user.id, action="radar.detail_view", resource=resource))
    db.flush()
    db.refresh(user)


# --- model --------------------------------------------------------------------


def test_unknown_action_is_rejected_by_the_database(make_user, test_db_session):
    user = make_user()
    with pytest.raises(IntegrityError):
        with test_db_session.begin_nested():
            test_db_session.add(Permission(user_id=user.id, action="layer.edit", resource="x"))
            test_db_session.flush()


def test_the_same_permission_cannot_be_stored_twice(make_user, test_db_session):
    user = make_user()
    test_db_session.add(Permission(user_id=user.id, action="radar.detail_view", resource="TSTA"))
    test_db_session.flush()
    with pytest.raises(IntegrityError):
        with test_db_session.begin_nested():
            test_db_session.add(Permission(user_id=user.id, action="radar.detail_view", resource="TSTA"))
            test_db_session.flush()


def test_deleting_a_user_deletes_its_permissions(make_user, test_db_session):
    user = make_user()
    test_db_session.add(Permission(user_id=user.id, action="radar.detail_view", resource="*"))
    test_db_session.flush()
    user_id = user.id
    test_db_session.delete(user)
    test_db_session.flush()
    assert test_db_session.query(Permission).filter_by(user_id=user_id).count() == 0


# --- rule: who may open which view (spec C §4, without companies) -----------------


def test_admin_sees_every_enabled_view(make_user, make_radar, test_db_session):
    admin = make_user(username="boss", role="admin")
    make_radar("TSTA")
    make_radar("TSTOFF", detail_view_enabled=False)
    views = perms.effective_radar_views(test_db_session, admin)
    assert "TSTA" in views and "TSTOFF" not in views


def test_viewer_without_permissions_sees_nothing(make_user, make_radar, test_db_session):
    make_radar("TSTA")
    assert perms.effective_radar_views(test_db_session, make_user()) == []


def test_viewer_sees_only_its_radars(make_user, make_radar, test_db_session):
    user = make_user()
    make_radar("TSTA")
    make_radar("TSTB")
    _grant(test_db_session, user, "TSTA")
    assert perms.effective_radar_views(test_db_session, user) == ["TSTA"]


def test_the_wildcard_covers_every_enabled_radar_present_and_future(make_user, make_radar, test_db_session):
    user = make_user()
    _grant(test_db_session, user, "*")
    make_radar("TSTA")  # added after the grant: still covered
    make_radar("TSTOFF", detail_view_enabled=False)
    views = perms.effective_radar_views(test_db_session, user)
    assert "TSTA" in views and "TSTOFF" not in views


def test_a_granted_radar_with_the_view_off_is_hidden(make_user, make_radar, test_db_session):
    user = make_user()
    make_radar("TSTOFF", detail_view_enabled=False)
    _grant(test_db_session, user, "TSTOFF")
    assert perms.effective_radar_views(test_db_session, user) == []


# --- replacing a user's list ------------------------------------------------------


def test_replace_stores_exactly_the_new_list(make_user, make_radar, test_db_session):
    admin = make_user(username="boss", role="admin")
    user = make_user()
    make_radar("TSTA")
    make_radar("TSTB")
    _grant(test_db_session, user, "TSTA")
    assert perms.replace_user_radar_views(test_db_session, user, ["TSTB", "TSTB"], admin) == ["TSTB"]
    assert perms.stored_radar_views(user) == ["TSTB"]


def test_replace_keeps_only_the_wildcard(make_user, make_radar, test_db_session):
    admin = make_user(username="boss", role="admin")
    user = make_user()
    make_radar("TSTA")
    assert perms.replace_user_radar_views(test_db_session, user, ["TSTA", "*"], admin) == ["*"]


def test_replace_with_an_unknown_radar_changes_nothing(make_user, make_radar, test_db_session):
    admin = make_user(username="boss", role="admin")
    user = make_user()
    make_radar("TSTA")
    _grant(test_db_session, user, "TSTA")
    with pytest.raises(perms.PermissionRuleError) as exc:
        perms.replace_user_radar_views(test_db_session, user, ["TSTA", "NOPE9"], admin)
    assert exc.value.status_code == 422
    assert perms.stored_radar_views(user) == ["TSTA"]


def test_replace_records_who_granted(make_user, make_radar, test_db_session):
    admin = make_user(username="boss", role="admin")
    user = make_user()
    make_radar("TSTA")
    perms.replace_user_radar_views(test_db_session, user, ["TSTA"], admin)
    assert user.permissions[0].granted_by == admin.id


# --- GET /api/v1/permissions/me -------------------------------------------------------


def test_my_permissions_requires_a_session(app_client):
    assert app_client.get("/api/v1/permissions/me").status_code == 401


def test_my_permissions_lists_the_resolved_views(app_client, make_user, make_radar, test_db_session):
    user = make_user()
    make_radar("TSTA")
    make_radar("TSTOFF", detail_view_enabled=False)
    _grant(test_db_session, user, "TSTA", "TSTOFF")
    login(app_client)
    response = app_client.get("/api/v1/permissions/me")
    assert response.status_code == 200
    assert response.json() == {"radar_detail_views": ["TSTA"]}


def test_an_account_created_with_google_starts_without_views(
    app_client, google_verifier, google_on, make_radar, test_db_session
):
    """Decision C15 also covers the accounts Google creates: they are viewers with no permissions."""
    make_radar("TSTA")
    google_verifier.identity = GoogleIdentity(sub="g-77", email="nuevo@gmail.com", email_verified=True, name="Nuevo")
    assert app_client.post("/api/v1/auth/google", json={"credential": "t"}).status_code == 200
    response = app_client.get("/api/v1/permissions/me")
    assert response.status_code == 200
    assert response.json() == {"radar_detail_views": []}


# --- PUT /api/v1/admin/users/{id}/permissions -------------------------------------------


def _admin_session(app_client, make_user):
    admin = make_user(username="boss", role="admin")
    login(app_client, "boss")
    return admin


def test_admin_replaces_a_users_views(app_client, make_user, make_radar):
    _admin_session(app_client, make_user)
    user = make_user()
    make_radar("TSTA")
    response = app_client.put(f"/api/v1/admin/users/{user.id}/permissions", json={"radar_detail_view": ["TSTA"]})
    assert response.status_code == 200
    assert response.json()["radar_detail_views"] == ["TSTA"]


def test_admin_grants_every_view(app_client, make_user, make_radar):
    _admin_session(app_client, make_user)
    user = make_user()
    make_radar("TSTA")
    body = {"radar_detail_view": ["TSTA", "*"]}
    assert app_client.put(f"/api/v1/admin/users/{user.id}/permissions", json=body).json()["radar_detail_views"] == ["*"]


def test_an_unknown_radar_is_422(app_client, make_user):
    _admin_session(app_client, make_user)
    user = make_user()
    body = {"radar_detail_view": ["NOPE9"]}
    assert app_client.put(f"/api/v1/admin/users/{user.id}/permissions", json=body).status_code == 422


def test_an_unknown_user_is_404(app_client, make_user):
    _admin_session(app_client, make_user)
    body = {"radar_detail_view": []}
    assert app_client.put("/api/v1/admin/users/999999999/permissions", json=body).status_code == 404


def test_a_viewer_cannot_assign_views(app_client, make_user):
    user = make_user()
    login(app_client)
    body = {"radar_detail_view": ["*"]}
    assert app_client.put(f"/api/v1/admin/users/{user.id}/permissions", json=body).status_code == 403


def test_the_user_list_shows_each_users_views(app_client, make_user, make_radar, test_db_session):
    _admin_session(app_client, make_user)
    user = make_user()
    make_radar("TSTA")
    _grant(test_db_session, user, "TSTA")
    listed = next(u for u in app_client.get("/api/v1/admin/users").json() if u["id"] == user.id)
    assert listed["radar_detail_views"] == ["TSTA"]


# --- deleting a radar --------------------------------------------------------------------


def test_deleting_a_radar_deletes_its_permissions(app_client, make_user, make_radar, test_db_session):
    _admin_session(app_client, make_user)
    user = make_user()
    make_radar("TSTA")
    _grant(test_db_session, user, "TSTA")
    assert app_client.delete("/api/v1/admin/radars/TSTA").status_code == 204
    assert test_db_session.query(Permission).filter_by(resource="TSTA").count() == 0


# --- two admins saving the same user at once ------------------------------------------------


def test_replace_locks_the_user_row_before_touching_the_list(make_user, make_radar, test_db_session):
    """Two admins saving the same user at the same moment would both delete the old rows and insert the new ones, and
    the second would break the unique constraint (a 500). The user row is locked first (SELECT ... FOR UPDATE), so the
    second request waits for the first and then saves its own list."""
    from sqlalchemy import event

    admin = make_user(username="boss", role="admin")
    user = make_user()
    make_radar("TSTA")
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = test_db_session.get_bind()
    event.listen(engine, "before_cursor_execute", capture)
    try:
        perms.replace_user_radar_views(test_db_session, user, ["TSTA"], admin)
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    lock = next((i for i, sql in enumerate(statements) if "FOR UPDATE" in sql), None)
    first_write = next((i for i, sql in enumerate(statements) if sql.lstrip().startswith(("DELETE", "INSERT"))), None)
    assert lock is not None, "the user row was never locked"
    assert first_write is None or lock < first_write, "the list was changed before the lock"
