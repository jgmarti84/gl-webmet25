# tests/auth/test_move_user.py
"""Moving an existing account into, between or out of companies (spec C, follow-up).

Rules: only the general admin moves accounts; only viewers move (never a company admin or the general admin); the
account takes a seat in the new company and gets a COPY of its views (its old list is replaced, not intersected);
its sessions are closed. A company admin who tries to create a user that already exists is told to ask the general
admin.
"""

import pytest

from api.app.auth import organizations as orgs
from api.app.auth import permissions as perms
from api.app.auth import user_admin
from radar_db.models import Permission

from .conftest import TEST_PASSWORD, login


def _own(db, user, *resources):
    """Store a user's own detail-view permissions, bypassing the service."""
    for resource in resources:
        db.add(Permission(user_id=user.id, action="radar.detail_view", resource=resource))
    db.flush()
    db.refresh(user)


def _member_data(username):
    return {"username": username, "password": TEST_PASSWORD, "full_name": None, "email": None}


def _give_admin(db, org, actor, username):
    """A viewer can only join a company that has an active admin: give it one (it takes a seat)."""
    return orgs.create_member(db, org.id, _member_data(username), "org_admin", actor)


@pytest.fixture
def boss(make_user):
    return make_user(username="boss", role="admin")


# --- the service ----------------------------------------------------------------------------------------------


def test_a_loose_account_joins_a_company_and_takes_a_seat(make_user, make_org, make_radar, boss, test_db_session):
    make_radar("TSTA")
    org = make_org(views=["TSTA"])
    _give_admin(test_db_session, org, boss, "jefe")
    loner = make_user(username="suelto")
    user_admin.update_user(test_db_session, boss, loner, {"organization_id": org.id})
    assert loner.organization_id == org.id
    assert orgs.seats_used(test_db_session, org) == 2


def test_its_old_views_are_replaced_by_the_company_ones_not_intersected(
    make_user, make_org, make_radar, boss, test_db_session
):
    make_radar("TSTA")
    make_radar("TSTB")
    make_radar("TSTC")
    org = make_org(views=["TSTA", "TSTC"])
    _give_admin(test_db_session, org, boss, "jefe")
    loner = make_user(username="suelto")
    _own(test_db_session, loner, "TSTA", "TSTB")
    user_admin.update_user(test_db_session, boss, loner, {"organization_id": org.id})
    # TSTB (its own, not the company's) is gone and TSTC (the company's, not its own) is there: a copy, no cut.
    assert perms.stored_radar_views(loner) == ["TSTA", "TSTC"]


def test_joining_closes_its_sessions(make_user, make_org, boss, test_db_session):
    org = make_org()
    _give_admin(test_db_session, org, boss, "jefe")
    loner = make_user(username="suelto")
    before = loner.token_version
    user_admin.update_user(test_db_session, boss, loner, {"organization_id": org.id})
    assert loner.token_version > before


def test_a_full_company_refuses_and_the_account_stays_as_it_was(make_user, make_org, make_radar, boss, test_db_session):
    make_radar("TSTA")
    org = make_org(seat_limit=1, views=["TSTA"])
    orgs.create_member(test_db_session, org.id, _member_data("uno"), "viewer", boss)
    loner = make_user(username="suelto")
    _own(test_db_session, loner, "TSTB")
    with pytest.raises(user_admin.UserRuleError) as exc:
        user_admin.update_user(test_db_session, boss, loner, {"organization_id": org.id})
    assert exc.value.status_code == 409
    assert loner.organization_id is None
    assert perms.stored_radar_views(loner) == ["TSTB"]


def test_an_inactive_company_does_not_receive_people(make_user, make_org, boss, test_db_session):
    org = make_org(is_active=False)
    loner = make_user(username="suelto")
    with pytest.raises(user_admin.UserRuleError) as exc:
        user_admin.update_user(test_db_session, boss, loner, {"organization_id": org.id})
    assert exc.value.status_code == 409
    assert loner.organization_id is None


def test_an_unknown_company_is_404(make_user, boss, test_db_session):
    loner = make_user(username="suelto")
    with pytest.raises(user_admin.UserRuleError) as exc:
        user_admin.update_user(test_db_session, boss, loner, {"organization_id": 999999999})
    assert exc.value.status_code == 404


def test_an_inactive_account_joins_without_taking_a_seat_and_needs_one_to_come_back(
    make_user, make_org, boss, test_db_session
):
    org = make_org(seat_limit=1)
    orgs.create_member(test_db_session, org.id, _member_data("uno"), "viewer", boss)  # the only seat
    sleeper = make_user(username="dormido", is_active=False)
    user_admin.update_user(test_db_session, boss, sleeper, {"organization_id": org.id})
    assert sleeper.organization_id == org.id
    assert orgs.seats_used(test_db_session, org) == 1
    with pytest.raises(user_admin.UserRuleError) as exc:
        user_admin.update_user(test_db_session, boss, sleeper, {"is_active": True})
    assert exc.value.status_code == 409


def test_moving_between_companies_frees_one_seat_and_takes_the_other(
    make_user, make_org, make_radar, boss, test_db_session
):
    make_radar("TSTA")
    make_radar("TSTB")
    org_a = make_org(name="Test Org A", views=["TSTA"])
    org_b = make_org(name="Test Org B", views=["TSTB"])
    _give_admin(test_db_session, org_a, boss, "jefe-a")
    _give_admin(test_db_session, org_b, boss, "jefe-b")
    member = orgs.create_member(test_db_session, org_a.id, _member_data("juan"), "viewer", boss)
    user_admin.update_user(test_db_session, boss, member, {"organization_id": org_b.id})
    assert member.organization_id == org_b.id
    assert orgs.seats_used(test_db_session, org_a) == 1  # only its admin is left
    assert orgs.seats_used(test_db_session, org_b) == 2
    assert perms.stored_radar_views(member) == ["TSTB"]


def test_leaving_a_company_frees_the_seat_and_removes_its_views(make_user, make_org, make_radar, boss, test_db_session):
    make_radar("TSTA")
    org = make_org(views=["TSTA"])
    member = orgs.create_member(test_db_session, org.id, _member_data("juan"), "viewer", boss)
    assert perms.stored_radar_views(member) == ["TSTA"]  # the copy of the company's list it got when it joined
    user_admin.update_user(test_db_session, boss, member, {"organization_id": None})
    assert member.organization_id is None
    assert orgs.seats_used(test_db_session, org) == 0
    assert perms.stored_radar_views(member) == []  # what the institution gave goes away with the person


def test_asking_for_the_company_it_already_has_changes_nothing(make_user, make_org, make_radar, boss, test_db_session):
    """The panel sends the whole form; saving it with the same company must not reset the views the admin trimmed."""
    make_radar("TSTA")
    make_radar("TSTB")
    org = make_org(views=["TSTA", "TSTB"])
    member = orgs.create_member(test_db_session, org.id, _member_data("juan"), "viewer", boss)
    perms.replace_user_radar_views(test_db_session, member, ["TSTA"], boss)
    before = member.token_version
    user_admin.update_user(test_db_session, boss, member, {"organization_id": org.id})
    assert perms.stored_radar_views(member) == ["TSTA"]
    assert member.token_version == before


def test_a_company_admin_cannot_be_moved_and_is_taken_out_only_if_the_company_keeps_an_admin(
    make_user, make_org, boss, test_db_session
):
    org_a = make_org(name="Test Org A")
    org_b = make_org(name="Test Org B")
    orgboss = orgs.create_member(test_db_session, org_a.id, _member_data("jefe"), "org_admin", boss)
    with pytest.raises(user_admin.UserRuleError) as exc:
        user_admin.update_user(test_db_session, boss, orgboss, {"organization_id": org_b.id})
    assert exc.value.status_code == 422
    assert orgboss.organization_id == org_a.id
    # With another active user left and no other admin, taking it out is refused (409) and nothing changes.
    orgs.create_member(test_db_session, org_a.id, _member_data("juan"), "viewer", boss)
    with pytest.raises(user_admin.UserRuleError) as exc:
        user_admin.update_user(test_db_session, boss, orgboss, {"organization_id": None})
    assert exc.value.status_code == 409
    assert orgboss.organization_id == org_a.id and orgboss.role == "org_admin"
    # With a second admin it goes in one step: it becomes a viewer with no company, and frees its seat.
    _give_admin(test_db_session, org_a, boss, "jefe2")
    user_admin.update_user(test_db_session, boss, orgboss, {"organization_id": None})
    assert orgboss.organization_id is None and orgboss.role == "viewer"
    assert orgs.seats_used(test_db_session, org_a) == 2


def test_the_general_admin_cannot_join_a_company(make_user, make_org, boss, test_db_session):
    org = make_org()
    other_admin = make_user(username="boss2", role="admin")
    with pytest.raises(user_admin.UserRuleError) as exc:
        user_admin.update_user(test_db_session, boss, other_admin, {"organization_id": org.id})
    assert exc.value.status_code == 422


def test_only_the_general_admin_moves_accounts(make_user, make_org, test_db_session, boss):
    """Defense in depth: the company panel already drops the field, but the rule lives in the service too."""
    org_a = make_org(name="Test Org A")
    org_b = make_org(name="Test Org B")
    orgboss = orgs.create_member(test_db_session, org_a.id, _member_data("jefe"), "org_admin", boss)
    member = orgs.create_member(test_db_session, org_a.id, _member_data("juan"), "viewer", boss)
    with pytest.raises(user_admin.UserRuleError) as exc:
        user_admin.update_user(test_db_session, orgboss, member, {"organization_id": org_b.id})
    assert exc.value.status_code == 403
    assert member.organization_id == org_a.id


# --- the HTTP endpoints ---------------------------------------------------------------------------------------


def test_the_admin_moves_an_account_through_the_api(app_client, make_user, make_org, make_radar):
    make_radar("TSTA")
    org = make_org(views=["TSTA"])
    make_user(username="boss", role="admin")
    make_user(username="jefe", role="org_admin", organization_id=org.id)
    loner = make_user(username="suelto")
    login(app_client, "boss")
    response = app_client.patch(f"/api/v1/admin/users/{loner.id}", json={"organization_id": org.id})
    assert response.status_code == 200
    body = response.json()
    assert body["organization_id"] == org.id and body["organization_name"] == "Test Org A"
    assert body["radar_detail_views"] == ["TSTA"]


def test_the_admin_takes_an_account_out_of_a_company_through_the_api(app_client, make_user, make_org, test_db_session):
    org = make_org()
    boss = make_user(username="boss", role="admin")
    member = orgs.create_member(test_db_session, org.id, _member_data("juan"), "viewer", boss)
    login(app_client, "boss")
    response = app_client.patch(f"/api/v1/admin/users/{member.id}", json={"organization_id": None})
    assert response.status_code == 200
    assert response.json()["organization_id"] is None


def test_a_patch_without_the_field_leaves_the_company_alone(app_client, make_user, make_org, test_db_session):
    org = make_org()
    boss = make_user(username="boss", role="admin")
    member = orgs.create_member(test_db_session, org.id, _member_data("juan"), "viewer", boss)
    login(app_client, "boss")
    response = app_client.patch(f"/api/v1/admin/users/{member.id}", json={"full_name": "Juan"})
    assert response.status_code == 200
    assert response.json()["organization_id"] == org.id


def test_a_company_admin_cannot_move_anyone_through_its_panel(app_client, make_user, make_org, test_db_session):
    org_a = make_org(name="Test Org A")
    org_b = make_org(name="Test Org B")
    boss = make_user(username="boss", role="admin")
    orgs.create_member(test_db_session, org_a.id, _member_data("jefe"), "org_admin", boss)
    member = orgs.create_member(test_db_session, org_a.id, _member_data("juan"), "viewer", boss)
    login(app_client, "jefe")
    response = app_client.patch(f"/api/v1/org/users/{member.id}", json={"organization_id": org_b.id})
    assert response.status_code in (200, 403, 422)
    assert member.organization_id == org_a.id  # whatever the answer, the account did not move


def test_a_viewer_cannot_use_the_move(app_client, make_user, make_org):
    org = make_org()
    make_user(username="otro")
    loner = make_user(username="alice")
    login(app_client, "alice")
    response = app_client.patch(f"/api/v1/admin/users/{loner.id}", json={"organization_id": org.id})
    assert response.status_code == 403


# --- the message to a company admin who adds someone who already has an account ------------------------------------


def test_adding_a_taken_username_tells_the_company_admin_to_ask_the_general_admin(
    app_client, make_user, make_org, test_db_session
):
    org = make_org()
    boss = make_user(username="boss", role="admin")
    orgs.create_member(test_db_session, org.id, _member_data("jefe"), "org_admin", boss)
    make_user(username="existente")
    login(app_client, "jefe")
    response = app_client.post("/api/v1/org/users", json={"username": "existente", "password": TEST_PASSWORD})
    assert response.status_code == 409
    assert "administrador general" in response.json()["detail"]


def test_adding_a_taken_mail_tells_the_company_admin_to_ask_the_general_admin(
    app_client, make_user, make_org, test_db_session
):
    org = make_org()
    boss = make_user(username="boss", role="admin")
    orgs.create_member(test_db_session, org.id, _member_data("jefe"), "org_admin", boss)
    make_user(username="existente", email="existente@example.com")
    login(app_client, "jefe")
    body = {"username": "nuevo", "password": TEST_PASSWORD, "email": "existente@example.com"}
    response = app_client.post("/api/v1/org/users", json=body)
    assert response.status_code == 409
    assert "administrador general" in response.json()["detail"]


def test_a_full_company_still_gets_the_seats_message_not_the_account_one(
    app_client, make_user, make_org, test_db_session
):
    org = make_org(seat_limit=1)
    boss = make_user(username="boss", role="admin")
    orgs.create_member(test_db_session, org.id, _member_data("jefe"), "org_admin", boss)
    login(app_client, "jefe")
    response = app_client.post("/api/v1/org/users", json={"username": "nuevo", "password": TEST_PASSWORD})
    assert response.status_code == 409
    assert "lugares" in response.json()["detail"]
    assert "administrador general" not in response.json()["detail"]


def test_the_general_admin_creating_a_taken_account_keeps_the_plain_message(app_client, make_user, make_org):
    org = make_org()
    make_user(username="boss", role="admin")
    make_user(username="existente")
    login(app_client, "boss")
    body = {"username": "existente", "password": TEST_PASSWORD, "role": "viewer", "organization_id": org.id}
    response = app_client.post("/api/v1/admin/users", json=body)
    assert response.status_code == 409
    assert "administrador general" not in response.json()["detail"]
