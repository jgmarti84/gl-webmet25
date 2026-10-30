# tests/auth/test_organizations.py
"""Company accounts (spec C, plan C-2): organizations, company admins, seats and company permissions."""

import pytest
from sqlalchemy.exc import IntegrityError

from api.app.auth import organizations as orgs
from api.app.auth import permissions as perms
from api.app.auth import user_admin
from api.app.auth.google import GoogleIdentity
from radar_db.models import Organization, Permission

from .conftest import TEST_PASSWORD, login


@pytest.fixture
def make_org(test_db_session):
    """Factory for organizations inside the rolled-back test transaction."""

    def _make(name="Test Org A", seat_limit=3, is_active=True, views=()):
        org = Organization(name=name, seat_limit=seat_limit, is_active=is_active)
        test_db_session.add(org)
        test_db_session.flush()
        for resource in views:
            test_db_session.add(Permission(organization_id=org.id, action="radar.detail_view", resource=resource))
        test_db_session.flush()
        test_db_session.refresh(org)
        return org

    return _make


def _rejected(db, obj) -> None:
    """Assert the database refuses to store `obj` (inside a savepoint, so the test can go on)."""
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(obj)
            db.flush()


def _member_data(username):
    return {"username": username, "password": TEST_PASSWORD, "full_name": None, "email": None}


def _own(db, user, *resources):
    """Store a user's own detail-view permissions, bypassing the service."""
    for resource in resources:
        db.add(Permission(user_id=user.id, action="radar.detail_view", resource=resource))
    db.flush()
    db.refresh(user)


# --- model --------------------------------------------------------------------------------


def test_a_company_admin_needs_a_company(make_user, test_db_session):
    user = make_user()
    with pytest.raises(IntegrityError):
        with test_db_session.begin_nested():
            user.role = "org_admin"
            test_db_session.flush()


def test_the_general_admin_cannot_belong_to_a_company(make_user, make_org, test_db_session):
    org = make_org()
    admin = make_user(username="boss", role="admin")
    with pytest.raises(IntegrityError):
        with test_db_session.begin_nested():
            admin.organization_id = org.id
            test_db_session.flush()


def test_a_permission_belongs_to_a_user_or_a_company_not_both(make_user, make_org, test_db_session):
    user = make_user()
    org = make_org()
    _rejected(
        test_db_session, Permission(user_id=user.id, organization_id=org.id, action="radar.detail_view", resource="*")
    )
    _rejected(test_db_session, Permission(action="radar.detail_view", resource="*"))


def test_the_seat_limit_must_be_positive(test_db_session):
    _rejected(test_db_session, Organization(name="Test Org Zero", seat_limit=0))


def test_company_names_are_unique(make_org, test_db_session):
    make_org(name="Test Org A")
    _rejected(test_db_session, Organization(name="Test Org A", seat_limit=1))


# --- inactive company -----------------------------------------------------------------------


def test_a_user_of_an_inactive_company_cannot_log_in(app_client, make_user, make_org):
    org = make_org(is_active=False)
    make_user(organization_id=org.id)
    response = app_client.post("/api/v1/auth/login", json={"username": "alice", "password": TEST_PASSWORD})
    assert response.status_code == 401


def test_deactivating_the_company_cuts_existing_sessions(app_client, make_user, make_org, test_db_session):
    org = make_org()
    make_user(organization_id=org.id)
    login(app_client)
    org.is_active = False
    test_db_session.flush()
    assert app_client.get("/api/v1/auth/me").status_code == 401
    assert app_client.post("/api/v1/auth/refresh").status_code == 401


def test_a_user_of_an_inactive_company_cannot_sign_in_with_google(
    client, google_verifier, google_on, make_user, make_org
):
    """Login with Google (already in dev) must follow the same rule as the password login."""
    org = make_org(is_active=False)
    make_user(username="ana", email="ana@gmail.com", organization_id=org.id)
    google_verifier.identity = GoogleIdentity(sub="g-1", email="ana@gmail.com", email_verified=True, name="Ana")
    response = client.post("/api/v1/auth/google", json={"credential": "t"})
    assert response.status_code == 403
    assert response.json()["code"] == "account_disabled"
    assert client.get("/api/v1/auth/me").status_code == 401


def test_a_company_admin_can_sign_in_with_google(client, google_verifier, google_on, make_user, make_org):
    """Decision C19: only the general admin is kept out of Google; a company admin comes in."""
    org = make_org()
    make_user(username="jefe", role="org_admin", email="jefe@gmail.com", organization_id=org.id)
    google_verifier.identity = GoogleIdentity(sub="g-2", email="jefe@gmail.com", email_verified=True, name="Jefe")
    response = client.post("/api/v1/auth/google", json={"credential": "t"})
    assert response.status_code == 200
    assert response.json()["role"] == "org_admin"


# --- views with companies (spec C §4) ------------------------------------------------------------


def test_a_company_admin_sees_the_company_views(make_user, make_org, make_radar, test_db_session):
    make_radar("TSTA")
    make_radar("TSTB")
    org = make_org(views=["TSTA"])
    admin = make_user(username="orgboss", role="org_admin", organization_id=org.id)
    assert perms.effective_radar_views(test_db_session, admin) == ["TSTA"]


def test_a_member_sees_its_list_cut_by_the_company(make_user, make_org, make_radar, test_db_session):
    make_radar("TSTA")
    make_radar("TSTB")
    org = make_org(views=["TSTA"])
    member = make_user(organization_id=org.id)
    _own(test_db_session, member, "TSTA", "TSTB")
    assert perms.effective_radar_views(test_db_session, member) == ["TSTA"]


def test_the_wildcard_on_either_side(make_user, make_org, make_radar, test_db_session):
    make_radar("TSTA")
    make_radar("TSTB")
    everything = make_org(name="Test Org A", views=["*"])
    member_a = make_user(organization_id=everything.id)
    _own(test_db_session, member_a, "TSTA")
    assert perms.effective_radar_views(test_db_session, member_a) == ["TSTA"]

    some = make_org(name="Test Org B", views=["TSTA", "TSTB"])
    member_b = make_user(username="bob", organization_id=some.id)
    _own(test_db_session, member_b, "*")
    assert {"TSTA", "TSTB"} <= set(perms.effective_radar_views(test_db_session, member_b))


def test_the_company_losing_a_radar_hides_it_from_its_members(make_user, make_org, make_radar, test_db_session):
    make_radar("TSTA")
    org = make_org(views=["TSTA"])
    member = make_user(organization_id=org.id)
    _own(test_db_session, member, "TSTA")
    admin = make_user(username="boss", role="admin")
    perms.replace_org_radar_views(test_db_session, org, [], admin)
    assert perms.effective_radar_views(test_db_session, member) == []
    assert perms.stored_radar_views(member) == ["TSTA"]  # the member's own list is untouched (decision C6)


def test_a_company_admin_cannot_give_more_than_the_company_has(make_user, make_org, make_radar, test_db_session):
    make_radar("TSTA")
    make_radar("TSTB")
    org = make_org(views=["TSTA"])
    boss = make_user(username="orgboss", role="org_admin", organization_id=org.id)
    member = make_user(organization_id=org.id)
    for wanted in (["TSTB"], ["*"]):
        with pytest.raises(perms.PermissionRuleError) as exc:
            perms.replace_user_radar_views(test_db_session, member, wanted, boss, within_company=True)
        assert exc.value.status_code == 403
    assert perms.replace_user_radar_views(test_db_session, member, ["TSTA"], boss, within_company=True) == ["TSTA"]


def test_a_company_with_every_view_lets_its_admin_give_anything(make_user, make_org, make_radar, test_db_session):
    make_radar("TSTB")
    org = make_org(views=["*"])
    boss = make_user(username="orgboss", role="org_admin", organization_id=org.id)
    member = make_user(organization_id=org.id)
    assert perms.replace_user_radar_views(test_db_session, member, ["*"], boss, within_company=True) == ["*"]


def test_replacing_the_company_list_locks_the_company_row(make_user, make_org, make_radar, test_db_session):
    """Same protection as the user's list (C-1): two admins saving one company at the same moment would both delete
    and insert the same rows. The company row is locked first (SELECT ... FOR UPDATE), before any write."""
    from sqlalchemy import event

    make_radar("TSTA")
    org = make_org()
    admin = make_user(username="boss", role="admin")
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = test_db_session.get_bind()
    event.listen(engine, "before_cursor_execute", capture)
    try:
        perms.replace_org_radar_views(test_db_session, org, ["TSTA"], admin)
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    lock = next((i for i, sql in enumerate(statements) if "FOR UPDATE" in sql), None)
    first_write = next((i for i, sql in enumerate(statements) if sql.lstrip().startswith(("DELETE", "INSERT"))), None)
    assert lock is not None, "the company row was never locked"
    assert first_write is None or lock < first_write, "the list was changed before the lock"


# --- seats and company users (spec C §5) ------------------------------------------------------------


def test_a_new_member_starts_with_the_company_views(make_user, make_org, make_radar, test_db_session):
    make_radar("TSTA")
    org = make_org(views=["TSTA"])
    boss = make_user(username="boss", role="admin")
    member = orgs.create_member(test_db_session, org.id, _member_data("nuevo"), "viewer", boss)
    assert member.organization_id == org.id and member.role == "viewer"
    assert perms.stored_radar_views(member) == ["TSTA"]


def test_a_full_company_cannot_add_users(make_user, make_org, test_db_session):
    org = make_org(seat_limit=1)
    boss = make_user(username="boss", role="admin")
    orgs.create_member(test_db_session, org.id, _member_data("uno"), "viewer", boss)
    with pytest.raises(orgs.OrgRuleError) as exc:
        orgs.create_member(test_db_session, org.id, _member_data("dos"), "viewer", boss)
    assert exc.value.status_code == 409


def test_deactivating_frees_a_seat_and_reactivating_needs_one(make_user, make_org, test_db_session):
    org = make_org(seat_limit=1)
    boss = make_user(username="boss", role="admin")
    first = orgs.create_member(test_db_session, org.id, _member_data("uno"), "viewer", boss)
    user_admin.update_user(test_db_session, boss, first, {"is_active": False})
    orgs.create_member(test_db_session, org.id, _member_data("dos"), "viewer", boss)  # the freed seat
    with pytest.raises(user_admin.UserRuleError) as exc:
        user_admin.update_user(test_db_session, boss, first, {"is_active": True})
    assert exc.value.status_code == 409


def test_lowering_the_limit_deactivates_nobody(make_user, make_org, test_db_session):
    org = make_org(seat_limit=2)
    boss = make_user(username="boss", role="admin")
    orgs.create_member(test_db_session, org.id, _member_data("uno"), "viewer", boss)
    orgs.create_member(test_db_session, org.id, _member_data("dos"), "viewer", boss)
    orgs.update_org(test_db_session, org, {"seat_limit": 1})
    assert orgs.seats_used(test_db_session, org) == 2
    with pytest.raises(orgs.OrgRuleError):
        orgs.create_member(test_db_session, org.id, _member_data("tres"), "viewer", boss)


def test_only_a_company_user_can_become_company_admin(make_user, test_db_session):
    boss = make_user(username="boss", role="admin")
    loner = make_user()
    with pytest.raises(user_admin.UserRuleError) as exc:
        user_admin.update_user(test_db_session, boss, loner, {"role": "org_admin"})
    assert exc.value.status_code == 422


def test_a_company_user_cannot_become_general_admin(make_user, make_org, test_db_session):
    org = make_org()
    boss = make_user(username="boss", role="admin")
    member = orgs.create_member(test_db_session, org.id, _member_data("uno"), "viewer", boss)
    with pytest.raises(user_admin.UserRuleError) as exc:
        user_admin.update_user(test_db_session, boss, member, {"role": "admin"})
    assert exc.value.status_code == 422


def test_demoting_a_company_admin_recopies_the_company_views(make_user, make_org, make_radar, test_db_session):
    make_radar("TSTA")
    make_radar("TSTB")
    org = make_org(views=["TSTA"])
    boss = make_user(username="boss", role="admin")
    orgboss = orgs.create_member(test_db_session, org.id, _member_data("jefe"), "org_admin", boss)
    perms.replace_org_radar_views(test_db_session, org, ["TSTA", "TSTB"], boss)
    user_admin.update_user(test_db_session, boss, orgboss, {"role": "viewer"})
    assert perms.stored_radar_views(orgboss) == ["TSTA", "TSTB"]


# --- /api/v1/admin/organizations and company fields on /admin/users ----------------------------------


def _as_admin(app_client, make_user):
    make_user(username="boss", role="admin")
    login(app_client, "boss")


def test_admin_creates_and_lists_companies(app_client, make_user):
    _as_admin(app_client, make_user)
    created = app_client.post("/api/v1/admin/organizations", json={"name": "Test Org A", "seat_limit": 5})
    assert created.status_code == 201
    body = created.json()
    assert body["seats_used"] == 0 and body["radar_detail_views"] == [] and body["is_active"] is True
    names = [o["name"] for o in app_client.get("/api/v1/admin/organizations").json()]
    assert "Test Org A" in names


def test_a_taken_company_name_is_409(app_client, make_user, make_org):
    _as_admin(app_client, make_user)
    make_org(name="Test Org A")
    response = app_client.post("/api/v1/admin/organizations", json={"name": "Test Org A", "seat_limit": 1})
    assert response.status_code == 409


def test_admin_sets_company_views(app_client, make_user, make_org, make_radar):
    _as_admin(app_client, make_user)
    make_radar("TSTA")
    org = make_org()
    url = f"/api/v1/admin/organizations/{org.id}/permissions"
    response = app_client.put(url, json={"radar_detail_view": ["TSTA"]})
    assert response.status_code == 200 and response.json()["radar_detail_views"] == ["TSTA"]


def test_admin_creates_a_company_admin(app_client, make_user, make_org):
    _as_admin(app_client, make_user)
    org = make_org()
    body = {"username": "jefe", "password": TEST_PASSWORD, "role": "org_admin", "organization_id": org.id}
    response = app_client.post("/api/v1/admin/users", json=body)
    assert response.status_code == 201
    assert response.json()["organization_id"] == org.id and response.json()["organization_name"] == "Test Org A"


def test_admin_cannot_create_into_a_full_company(app_client, make_user, make_org):
    _as_admin(app_client, make_user)
    org = make_org(seat_limit=1)
    first = {"username": "uno", "password": TEST_PASSWORD, "role": "viewer", "organization_id": org.id}
    assert app_client.post("/api/v1/admin/users", json=first).status_code == 201
    second = {**first, "username": "dos"}
    assert app_client.post("/api/v1/admin/users", json=second).status_code == 409


def test_a_company_admin_without_company_is_422(app_client, make_user):
    _as_admin(app_client, make_user)
    body = {"username": "jefe", "password": TEST_PASSWORD, "role": "org_admin"}
    assert app_client.post("/api/v1/admin/users", json=body).status_code == 422


def test_an_unknown_company_is_404(app_client, make_user):
    _as_admin(app_client, make_user)
    assert app_client.get("/api/v1/admin/organizations/999999999").status_code == 404
    body = {"username": "xuno", "password": TEST_PASSWORD, "role": "viewer", "organization_id": 999999999}
    assert app_client.post("/api/v1/admin/users", json=body).status_code == 404


def test_a_viewer_cannot_manage_companies(app_client, make_user):
    make_user()
    login(app_client)
    assert app_client.get("/api/v1/admin/organizations").status_code == 403


# --- /api/v1/org (company admin) -----------------------------------------------------------------------


@pytest.fixture
def company(app_client, make_user, make_org, make_radar, test_db_session):
    """Org A (3 seats, views TSTA and TSTB) with its admin logged in, a member, and a user of another company."""
    make_radar("TSTA")
    make_radar("TSTB")
    org = make_org(seat_limit=3, views=["TSTA", "TSTB"])
    other = make_org(name="Test Org B")
    boss = make_user(username="boss", role="admin")
    orgboss = orgs.create_member(test_db_session, org.id, _member_data("jefe"), "org_admin", boss)
    member = orgs.create_member(test_db_session, org.id, _member_data("juan"), "viewer", boss)
    stranger = orgs.create_member(test_db_session, other.id, _member_data("ajeno"), "viewer", boss)
    login(app_client, "jefe")
    return {"org": org, "orgboss": orgboss, "member": member, "stranger": stranger}


def test_org_shows_the_own_company(app_client, company):
    body = app_client.get("/api/v1/org").json()
    assert body["name"] == "Test Org A" and body["seats_used"] == 2 and body["radar_detail_views"] == ["TSTA", "TSTB"]


def test_org_lists_only_its_users(app_client, company):
    names = {u["username"] for u in app_client.get("/api/v1/org/users").json()}
    assert names == {"jefe", "juan"}


def test_org_admin_creates_a_viewer_with_the_company_views(app_client, company):
    response = app_client.post("/api/v1/org/users", json={"username": "nueva", "password": TEST_PASSWORD})
    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "viewer" and body["organization_id"] == company["org"].id
    assert body["radar_detail_views"] == ["TSTA", "TSTB"]


def test_org_admin_cannot_go_over_the_seats(app_client, company):
    assert app_client.post("/api/v1/org/users", json={"username": "tres", "password": TEST_PASSWORD}).status_code == 201
    response = app_client.post("/api/v1/org/users", json={"username": "cuatro", "password": TEST_PASSWORD})
    assert response.status_code == 409


def test_org_admin_narrows_a_members_views(app_client, company):
    member = company["member"]
    response = app_client.put(f"/api/v1/org/users/{member.id}/permissions", json={"radar_detail_view": ["TSTA"]})
    assert response.status_code == 200 and response.json()["radar_detail_views"] == ["TSTA"]


def test_org_admin_cannot_give_what_the_company_lacks(app_client, company, make_radar):
    make_radar("TSTC")
    member = company["member"]
    body = {"radar_detail_view": ["TSTC"]}
    assert app_client.put(f"/api/v1/org/users/{member.id}/permissions", json=body).status_code == 403


def test_a_user_of_another_company_is_404(app_client, company):
    stranger = company["stranger"]
    assert app_client.patch(f"/api/v1/org/users/{stranger.id}", json={"full_name": "x"}).status_code == 404
    response = app_client.put(f"/api/v1/org/users/{stranger.id}/permissions", json={"radar_detail_view": []})
    assert response.status_code == 404


def test_org_admin_cannot_touch_another_company_admin(app_client, company, make_user, test_db_session):
    peer = orgs.create_member(
        test_db_session, company["org"].id, _member_data("otrojefe"), "org_admin", company["orgboss"]
    )
    assert app_client.patch(f"/api/v1/org/users/{peer.id}", json={"is_active": False}).status_code == 403


def test_org_admin_deactivates_and_reactivates_a_member(app_client, company):
    member = company["member"]
    assert app_client.patch(f"/api/v1/org/users/{member.id}", json={"is_active": False}).json()["is_active"] is False
    assert app_client.patch(f"/api/v1/org/users/{member.id}", json={"is_active": True}).json()["is_active"] is True


def test_org_admin_resets_a_members_password(app_client, company):
    member = company["member"]
    body = {"password": "otra-contrasena-larga-123"}
    assert app_client.post(f"/api/v1/org/users/{member.id}/reset-password", json=body).status_code == 204


def test_a_viewer_or_the_general_admin_cannot_use_org(app_client, make_user):
    make_user()
    login(app_client)
    assert app_client.get("/api/v1/org").status_code == 403
    make_user(username="boss", role="admin")
    login(app_client, "boss")
    assert app_client.get("/api/v1/org").status_code == 403
