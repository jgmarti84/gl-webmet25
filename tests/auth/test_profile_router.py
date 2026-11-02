# tests/auth/test_profile_router.py
"""The user's own profile (spec D): GET and PATCH /api/v1/profile, for every role."""

import pytest

from api.app.auth import organizations as orgs
from radar_db.models import Permission

from .conftest import TEST_PASSWORD, login

URL = "/api/v1/profile"
FIELDS = {
    "username",
    "full_name",
    "email",
    "role",
    "organization_name",
    "created_at",
    "last_login_at",
    "radar_detail_views",
}


def _member_data(username):
    return {"username": username, "password": TEST_PASSWORD, "full_name": None, "email": None}


def _own(db, user, *resources):
    """Store a user's own detail-view permissions, bypassing the service."""
    for resource in resources:
        db.add(Permission(user_id=user.id, action="radar.detail_view", resource=resource))
    db.flush()
    db.refresh(user)


# --- GET /profile --------------------------------------------------------------------------------------------


def test_a_viewer_reads_its_own_profile(app_client, make_user):
    make_user(username="ana", full_name="Ana Pérez", email="ana@example.com")
    login(app_client, "ana")
    response = app_client.get(URL)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == FIELDS
    assert body["username"] == "ana" and body["full_name"] == "Ana Pérez"
    assert body["email"] == "ana@example.com" and body["role"] == "viewer"
    assert body["organization_name"] is None
    assert body["radar_detail_views"] == []


def test_the_profile_is_never_somebody_elses(app_client, make_user):
    make_user(username="ana", full_name="Ana")
    make_user(username="beto", full_name="Beto")
    login(app_client, "beto")
    assert app_client.get(URL).json()["username"] == "beto"


def test_the_profile_lists_the_radars_the_user_may_open_with_their_titles(
    app_client, make_user, make_radar, test_db_session
):
    make_radar("TSTA")
    make_radar("TSTB")
    user = make_user(username="ana")
    _own(test_db_session, user, "TSTA")
    login(app_client, "ana")
    assert app_client.get(URL).json()["radar_detail_views"] == [{"code": "TSTA", "title": "Test TSTA"}]


def test_the_general_admin_sees_every_enabled_radar(app_client, make_user, make_radar):
    make_radar("TSTA")
    make_radar("TSTB", detail_view_enabled=False)
    make_user(username="boss", role="admin")
    login(app_client, "boss")
    codes = [view["code"] for view in app_client.get(URL).json()["radar_detail_views"]]
    assert "TSTA" in codes and "TSTB" not in codes


def test_a_company_member_sees_its_list_cut_by_the_company(
    app_client, make_user, make_org, make_radar, test_db_session
):
    make_radar("TSTA")
    make_radar("TSTB")
    org = make_org(views=["TSTA"])
    member = make_user(username="juan", organization_id=org.id)
    _own(test_db_session, member, "TSTA", "TSTB")
    login(app_client, "juan")
    body = app_client.get(URL).json()
    assert [view["code"] for view in body["radar_detail_views"]] == ["TSTA"]
    assert body["organization_name"] == "Test Org A"


def test_a_company_admin_reads_its_profile_with_the_company_name(app_client, make_user, make_org, test_db_session):
    org = make_org()
    boss = make_user(username="boss", role="admin")
    orgs.create_member(test_db_session, org.id, _member_data("jefe"), "org_admin", boss)
    login(app_client, "jefe")
    body = app_client.get(URL).json()
    assert body["role"] == "org_admin" and body["organization_name"] == "Test Org A"


def test_the_profile_needs_a_session(app_client):
    assert app_client.get(URL).status_code == 401
    assert app_client.patch(URL, json={"full_name": "x"}).status_code == 401


# --- PATCH /profile ------------------------------------------------------------------------------------------


def test_the_user_changes_its_own_name(app_client, make_user):
    make_user(username="ana", full_name="Ana")
    login(app_client, "ana")
    response = app_client.patch(URL, json={"full_name": "  Ana María Pérez  "})
    assert response.status_code == 200
    assert response.json()["full_name"] == "Ana María Pérez"  # trimmed
    assert app_client.get(URL).json()["full_name"] == "Ana María Pérez"


def test_an_empty_name_clears_it(app_client, make_user):
    make_user(username="ana", full_name="Ana")
    login(app_client, "ana")
    assert app_client.patch(URL, json={"full_name": "   "}).json()["full_name"] is None
    assert app_client.patch(URL, json={"full_name": None}).json()["full_name"] is None


def test_a_name_over_128_characters_is_a_422(app_client, make_user):
    make_user(username="ana", full_name="Ana")
    login(app_client, "ana")
    assert app_client.patch(URL, json={"full_name": "x" * 129}).status_code == 422
    assert app_client.patch(URL, json={"full_name": "x" * 128}).status_code == 200


def test_nothing_but_the_name_can_be_changed_through_the_profile(app_client, make_user, make_org, test_db_session):
    org = make_org()
    user = make_user(username="ana", full_name="Ana", email="ana@example.com")
    login(app_client, "ana")
    body = {
        "full_name": "Ana Nueva",
        "role": "admin",
        "email": "otro@example.com",
        "username": "otro",
        "organization_id": org.id,
        "is_active": False,
    }
    response = app_client.patch(URL, json=body)
    assert response.status_code == 200
    test_db_session.refresh(user)
    assert user.full_name == "Ana Nueva"
    assert (user.role, user.email, user.username) == ("viewer", "ana@example.com", "ana")
    assert user.organization_id is None and user.is_active is True


def test_a_patch_without_the_name_changes_nothing(app_client, make_user):
    make_user(username="ana", full_name="Ana")
    login(app_client, "ana")
    assert app_client.patch(URL, json={}).json()["full_name"] == "Ana"


@pytest.mark.parametrize("role", ["viewer", "org_admin", "admin"])
def test_every_role_can_change_its_own_name(app_client, make_user, make_org, test_db_session, role):
    boss = make_user(username="boss", role="admin")
    if role == "org_admin":
        org = make_org()
        orgs.create_member(test_db_session, org.id, _member_data("ana"), "org_admin", boss)
        login(app_client, "ana")
    elif role == "admin":
        login(app_client, "boss")
    else:
        make_user(username="ana")
        login(app_client, "ana")
    assert app_client.patch(URL, json={"full_name": "Nombre Nuevo"}).json()["full_name"] == "Nombre Nuevo"


def test_a_patch_from_a_foreign_origin_is_a_403(app_client, make_user):
    make_user(username="ana", full_name="Ana")
    login(app_client, "ana")
    response = app_client.patch(URL, json={"full_name": "x"}, headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert app_client.get(URL).json()["full_name"] == "Ana"
