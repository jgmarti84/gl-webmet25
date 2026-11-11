# tests/auth/test_tracking_tool.py
"""The storm tracking tool: a yes/no permission per user and per institution, intersected like the radar views.

The tracking service itself is never called here: these tests cover who has the tool, how it is stored and copied,
and the session probe nginx asks before letting a request reach the service.
"""

import pytest
from sqlalchemy.exc import IntegrityError

from radar_db.models import Invitation, Permission

from .conftest import login


def _rejected(db, obj) -> None:
    """Assert the database refuses to store `obj` (inside a savepoint, so the test can go on)."""
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(obj)
            db.flush()


# --- model --------------------------------------------------------------------------------------------------------


def test_the_tool_action_is_accepted(make_user, test_db_session):
    user = make_user()
    test_db_session.add(Permission(user_id=user.id, action="tool.tracking", resource="*"))
    test_db_session.flush()


def test_an_unknown_action_is_still_rejected(make_user, test_db_session):
    user = make_user()
    _rejected(test_db_session, Permission(user_id=user.id, action="tool.other", resource="*"))


def test_an_institution_admin_invitation_cannot_carry_tracking(make_org, test_db_session):
    from datetime import datetime, timedelta, timezone

    org = make_org()
    now = datetime.now(timezone.utc)
    _rejected(
        test_db_session,
        Invitation(
            email="x@ejemplo.com.ar",
            organization_id=org.id,
            role="org_admin",
            tools={"tracking": True},
            token_hash="a" * 64,
            expires_at=now + timedelta(days=1),
        ),
    )


# --- rules ---------------------------------------------------------------------------------------------------------

from api.app.auth import organizations as orgs  # noqa: E402
from api.app.auth import permissions as perms  # noqa: E402


def _tool(db, owner_kwargs) -> None:
    db.add(Permission(action="tool.tracking", resource="*", **owner_kwargs))
    db.flush()


def test_the_general_admin_always_has_it(make_user, test_db_session):
    admin = make_user(username="boss", role="admin")
    assert perms.effective_tools(test_db_session, admin) == {"tracking": True}


def test_a_loose_user_has_its_own(make_user, test_db_session):
    user = make_user()
    assert perms.effective_tools(test_db_session, user) == {"tracking": False}
    _tool(test_db_session, {"user_id": user.id})
    test_db_session.refresh(user)
    assert perms.effective_tools(test_db_session, user) == {"tracking": True}


def test_a_member_needs_its_own_and_the_institution(make_user, make_org, test_db_session):
    org = make_org()
    member = make_user(organization_id=org.id)
    _tool(test_db_session, {"user_id": member.id})
    test_db_session.refresh(member)
    assert perms.effective_tools(test_db_session, member) == {"tracking": False}  # institution lacks it
    _tool(test_db_session, {"organization_id": org.id})
    test_db_session.refresh(org)
    assert perms.effective_tools(test_db_session, member) == {"tracking": True}


def test_an_institution_admin_has_the_institution(make_user, make_org, test_db_session):
    org = make_org()
    boss = make_user(username="orgboss", role="org_admin", organization_id=org.id)
    assert perms.effective_tools(test_db_session, boss) == {"tracking": False}
    _tool(test_db_session, {"organization_id": org.id})
    test_db_session.refresh(org)
    assert perms.effective_tools(test_db_session, boss) == {"tracking": True}


def test_set_user_tools_puts_and_removes_the_row(make_user, test_db_session):
    admin = make_user(username="boss", role="admin")
    user = make_user()
    assert perms.set_user_tools(test_db_session, user, {"tracking": True}, admin) == {"tracking": True}
    assert perms.stored_tool(user, perms.TOOL_TRACKING) is True
    assert perms.set_user_tools(test_db_session, user, {"tracking": False}, admin) == {"tracking": False}
    assert perms.stored_tool(user, perms.TOOL_TRACKING) is False


def test_an_institution_admin_cannot_give_what_the_institution_lacks(make_user, make_org, test_db_session):
    org = make_org()
    boss = make_user(username="orgboss", role="org_admin", organization_id=org.id)
    member = make_user(organization_id=org.id)
    with pytest.raises(perms.PermissionRuleError) as exc:
        perms.set_user_tools(test_db_session, member, {"tracking": True}, boss, within_company=True)
    assert exc.value.status_code == 403
    # Taking it away is always allowed.
    assert perms.set_user_tools(test_db_session, member, {"tracking": False}, boss, within_company=True) == {
        "tracking": False
    }


def test_a_new_member_copies_the_institution_tool(make_user, make_org, test_db_session):
    admin = make_user(username="boss", role="admin")
    org = make_org()
    perms.set_org_tools(test_db_session, org, {"tracking": True}, admin)
    member = make_user(organization_id=org.id)
    perms.copy_company_views_to(test_db_session, member, admin)
    assert perms.stored_tool(member, perms.TOOL_TRACKING) is True


def test_leaving_the_institution_removes_the_tool(make_user, make_org, test_db_session):
    admin = make_user(username="boss", role="admin")
    org = make_org()
    perms.set_org_tools(test_db_session, org, {"tracking": True}, admin)
    member = make_user(organization_id=org.id)
    perms.copy_company_views_to(test_db_session, member, admin)
    orgs.leave_org(test_db_session, admin, member)
    assert perms.stored_tool(member, perms.TOOL_TRACKING) is False


def test_tracking_on_a_radar_needs_the_tool_and_the_view(make_user, make_radar, test_db_session):
    admin = make_user(username="boss", role="admin")
    make_radar("TSTA")
    make_radar("TSTB")
    user = make_user()
    perms.replace_user_radar_views(test_db_session, user, ["TSTA"], admin)
    assert perms.can_use_tracking_on(test_db_session, user, "TSTA") is False  # no tool
    perms.set_user_tools(test_db_session, user, {"tracking": True}, admin)
    assert perms.can_use_tracking_on(test_db_session, user, "TSTA") is True
    assert perms.can_use_tracking_on(test_db_session, user, "TSTB") is False  # tool, but no view of TSTB


# --- endpoints -----------------------------------------------------------------------------------------------------


def _as(client, make_user, username="boss", role="admin", **kwargs):
    make_user(username=username, role=role, **kwargs)
    login(client, username)
    return client


def test_my_permissions_include_the_tools(app_client, make_user):
    make_user()
    login(app_client)
    assert app_client.get("/api/v1/permissions/me").json()["tools"] == {"tracking": False}


def test_admin_sets_only_the_tool(app_client, make_user, make_radar, test_db_session):
    client = _as(app_client, make_user)
    make_radar("TSTA")
    user = make_user()
    perms.replace_user_radar_views(test_db_session, user, ["TSTA"], user)
    response = client.put(f"/api/v1/admin/users/{user.id}/permissions", json={"tools": {"tracking": True}})
    assert response.status_code == 200
    body = response.json()
    assert body["tools"] == {"tracking": True} and body["radar_detail_views"] == ["TSTA"]  # views untouched


def test_admin_sets_views_and_tool_together(app_client, make_user, make_radar):
    client = _as(app_client, make_user)
    make_radar("TSTA")
    user = make_user()
    body = {"radar_detail_view": ["TSTA"], "tools": {"tracking": True}}
    response = client.put(f"/api/v1/admin/users/{user.id}/permissions", json=body)
    assert response.json()["radar_detail_views"] == ["TSTA"] and response.json()["tools"] == {"tracking": True}


def test_an_empty_permissions_body_is_422(app_client, make_user):
    client = _as(app_client, make_user)
    user = make_user()
    assert client.put(f"/api/v1/admin/users/{user.id}/permissions", json={}).status_code == 422


def test_admin_sets_the_institution_tool(app_client, make_user, make_org):
    client = _as(app_client, make_user)
    org = make_org()
    response = client.put(f"/api/v1/admin/organizations/{org.id}/permissions", json={"tools": {"tracking": True}})
    assert response.status_code == 200 and response.json()["tools"] == {"tracking": True}


def test_institution_admin_cannot_give_tracking_the_institution_lacks(app_client, make_user, make_org):
    org = make_org()
    client = _as(app_client, make_user, username="orgboss", role="org_admin", organization_id=org.id)
    member = make_user(organization_id=org.id)
    response = client.put(f"/api/v1/org/users/{member.id}/permissions", json={"tools": {"tracking": True}})
    assert response.status_code == 403


def test_institution_admin_gives_tracking_the_institution_has(app_client, make_user, make_org, test_db_session):
    admin = make_user(username="boss", role="admin")
    org = make_org()
    perms.set_org_tools(test_db_session, org, {"tracking": True}, admin)
    client = _as(app_client, make_user, username="orgboss", role="org_admin", organization_id=org.id)
    member = make_user(organization_id=org.id)
    response = client.put(f"/api/v1/org/users/{member.id}/permissions", json={"tools": {"tracking": True}})
    assert response.status_code == 200 and response.json()["tools"] == {"tracking": True}


def test_institution_admin_creates_a_user_with_the_tool(app_client, make_user, make_org, test_db_session):
    admin = make_user(username="boss", role="admin")
    org = make_org()
    perms.set_org_tools(test_db_session, org, {"tracking": True}, admin)
    client = _as(app_client, make_user, username="orgboss", role="org_admin", organization_id=org.id)
    body = {"username": "nuevo", "password": "una-clave-larga-1!", "tools": {"tracking": False}}
    response = client.post("/api/v1/org/users", json=body)
    assert response.status_code == 201 and response.json()["tools"] == {"tracking": False}  # the choice wins


def test_create_an_institution_with_tracking(app_client, make_user):
    client = _as(app_client, make_user)
    body = {"name": "Test Org T", "seat_limit": 3, "tools": {"tracking": True}}
    response = client.post("/api/v1/admin/organizations", json=body)
    assert response.status_code == 201 and response.json()["tools"] == {"tracking": True}


# --- the session probe nginx asks ----------------------------------------------------------------------------------


def test_check_tool_without_session_is_401(app_client):
    assert app_client.get("/api/v1/auth/check", params={"tool": "tracking"}).status_code == 401


def test_check_tool_needs_the_tool(app_client, make_user, test_db_session):
    user = make_user()
    login(app_client)
    assert app_client.get("/api/v1/auth/check", params={"tool": "tracking"}).status_code == 403
    perms.set_user_tools(test_db_session, user, {"tracking": True}, user)
    assert app_client.get("/api/v1/auth/check", params={"tool": "tracking"}).status_code == 204


def test_check_tool_on_a_radar_needs_the_view_too(app_client, make_user, make_radar, test_db_session):
    make_radar("TSTA")
    make_radar("TSTB")
    user = make_user()
    perms.replace_user_radar_views(test_db_session, user, ["TSTA"], user)
    login(app_client)
    params = {"tool": "tracking", "radar": "TSTA"}
    assert app_client.get("/api/v1/auth/check", params=params).status_code == 403  # view, no tool
    perms.set_user_tools(test_db_session, user, {"tracking": True}, user)
    assert app_client.get("/api/v1/auth/check", params=params).status_code == 204
    assert app_client.get("/api/v1/auth/check", params={**params, "radar": "TSTB"}).status_code == 403


def test_check_rejects_a_malformed_radar_code(app_client, make_user):
    make_user()
    login(app_client)
    assert app_client.get("/api/v1/auth/check", params={"tool": "tracking", "radar": "../x"}).status_code == 422
