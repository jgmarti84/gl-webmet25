# tests/auth/test_org_delete.py
"""Deleting institutions: DELETE /api/v1/admin/organizations/{id}?users=block|unlink|delete.

Everything goes through the real application (`app_client`), the way the admin panel uses it. What is checked here:

* only the general admin deletes institutions (401 without a session, 403 for institution admins, viewers and foreign
  origins), an unknown id is 404, and a bad id or a bad `users` value is 422 before anything is touched;
* an institution without users is deleted, with its views and ALL its invitations (pending, cancelled...);
* with users and `users=block` (the default) nothing is deleted and the answer says how many users it has, inactive
  ones included;
* `users=unlink` sets every user free (an institution admin becomes a viewer, the views it had are gone, the
  sessions are closed, an inactive account stays inactive) and deletes the institution, even if it was the only admin;
* `users=delete` deletes every user with its sessions, tokens and views, even the only admin, and the institution;
* other institutions, their users and their invitations are never touched, and neither is the general admin.
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from api.app.auth import email_tokens, permissions
from api.app.config import settings
from radar_db.models import EmailToken, Invitation, Organization, Permission, User, UserSession

from .conftest import TEST_EMAIL_DOMAIN, login, token_from

ORG_URL = "/api/v1/admin/organizations"
INVITATIONS_URL = "/api/v1/admin/invitations"
PUBLIC_URL = "/api/v1/invitations"


@pytest.fixture
def boss(make_user):
    return make_user(username="boss", role="admin")


@pytest.fixture
def org(make_org, make_radar):
    make_radar("TSTA")
    return make_org(name="Test Org A", seat_limit=10, views=["TSTA"])


@pytest.fixture
def other_org(make_org):
    """A second institution that no test of this file may ever change."""
    return make_org(name="Test Org B", seat_limit=10, views=["TSTA"])


def _as(client, username):
    login(client, username)
    return client


def _delete(client, org_id, users=None):
    return client.delete(f"{ORG_URL}/{org_id}", params={} if users is None else {"users": users})


def _second_client():
    """Another browser: its own cookies, the same application (and the same test database session)."""
    from api.app.main import app

    return TestClient(app, base_url="http://testserver")


def _org_exists(db, org_id):
    db.expire_all()  # the database may have changed these rows (cascades), not the session
    return db.get(Organization, org_id) is not None


def _user(db, username):
    db.expire_all()
    return db.query(User).filter(User.username == username).one_or_none()


def _invite(client, org, email, role="viewer"):
    return client.post(INVITATIONS_URL, json={"email": email, "organization_id": org.id, "role": role})


def _invitations_of(db, org_id):
    return db.query(Invitation).filter(Invitation.organization_id == org_id).count()


@pytest.fixture
def team(make_user, org):
    """An institution with an admin, two readers (one with views of its own) and a sleeping reader."""
    return {
        "jefe": make_user(username="jefe", role="org_admin", organization_id=org.id),
        "ana": make_user(username="ana", organization_id=org.id),
        "beto": make_user(username="beto", organization_id=org.id),
        "dormido": make_user(username="dormido", organization_id=org.id, is_active=False),
    }


# --- who may use it ----------------------------------------------------------------------------------------------


def test_without_a_session_it_is_401(app_client, org, test_db_session):
    assert _delete(app_client, org.id).status_code == 401
    assert _org_exists(test_db_session, org.id)


@pytest.mark.parametrize("who", ["org_admin", "viewer"])
def test_only_the_general_admin_deletes_institutions(app_client, make_user, org, test_db_session, who):
    make_user(username="jefe", role="org_admin", organization_id=org.id)
    make_user(username="otro", organization_id=org.id)
    login(app_client, "jefe" if who == "org_admin" else "otro")
    for users in (None, "unlink", "delete"):
        assert _delete(app_client, org.id, users).status_code == 403
    assert _org_exists(test_db_session, org.id) and _user(test_db_session, "otro") is not None


def test_a_foreign_origin_is_refused(app_client, boss, org, test_db_session):
    client = _as(app_client, "boss")
    response = client.delete(f"{ORG_URL}/{org.id}", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403
    assert _org_exists(test_db_session, org.id)


def test_an_unknown_id_is_404_and_a_bad_id_is_422(app_client, boss):
    client = _as(app_client, "boss")
    assert _delete(client, 999999999).status_code == 404
    assert _delete(client, 999999999, "unlink").status_code == 404
    assert client.delete(f"{ORG_URL}/abc").status_code == 422
    assert client.delete(f"{ORG_URL}/1;DROP TABLE organizations").status_code == 422


@pytest.mark.parametrize("value", ["todos", "UNLINK", "Delete", "", "unlink,delete", "1"])
def test_a_bad_users_value_is_422_and_nothing_is_touched(app_client, boss, org, team, test_db_session, value):
    response = _as(app_client, "boss").delete(f"{ORG_URL}/{org.id}", params={"users": value})
    assert response.status_code == 422
    assert _org_exists(test_db_session, org.id) and _user(test_db_session, "ana").organization_id == org.id


def test_a_bad_users_value_is_refused_even_for_an_unknown_institution(app_client, boss):
    assert _as(app_client, "boss").delete(f"{ORG_URL}/999999999", params={"users": "todos"}).status_code == 422


# --- an institution without users -----------------------------------------------------------------------------------


def test_an_empty_institution_is_deleted_with_its_views_and_disappears_from_the_list(
    app_client, boss, org, test_db_session
):
    client = _as(app_client, "boss")
    assert test_db_session.query(Permission).filter(Permission.organization_id == org.id).count() == 1
    assert _delete(client, org.id).status_code == 204
    assert not _org_exists(test_db_session, org.id)
    assert test_db_session.query(Permission).filter(Permission.organization_id == org.id).count() == 0
    assert org.name not in [o["name"] for o in client.get(ORG_URL).json()]
    assert client.get(f"{ORG_URL}/{org.id}").status_code == 404
    assert _delete(client, org.id).status_code == 404  # already gone


@pytest.mark.parametrize("users", [None, "block", "unlink", "delete"])
def test_every_mode_deletes_an_empty_institution(app_client, boss, org, test_db_session, users):
    assert _delete(_as(app_client, "boss"), org.id, users).status_code == 204
    assert not _org_exists(test_db_session, org.id)


def test_the_name_of_a_deleted_institution_can_be_used_again(app_client, boss, org):
    client = _as(app_client, "boss")
    assert _delete(client, org.id).status_code == 204
    assert client.post(ORG_URL, json={"name": org.name, "seat_limit": 3}).status_code == 201


# --- block: an institution with users is not deleted ---------------------------------------------------------------


@pytest.mark.parametrize("users", [None, "block"])
def test_with_users_the_default_refuses_and_changes_nothing(app_client, boss, org, team, test_db_session, users):
    response = _delete(_as(app_client, "boss"), org.id, users)
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert org.name in detail and "4" in detail  # the admin, two readers and the sleeping one
    assert _org_exists(test_db_session, org.id)
    for name in team:
        assert _user(test_db_session, name).organization_id == org.id


def test_an_institution_with_only_inactive_users_is_refused_too(app_client, boss, org, make_user, test_db_session):
    make_user(username="dormido", organization_id=org.id, is_active=False)
    assert _delete(_as(app_client, "boss"), org.id).status_code == 409
    assert _org_exists(test_db_session, org.id)


# --- invitations --------------------------------------------------------------------------------------------------


@pytest.fixture
def mails(registration_on, mailer, monkeypatch):
    monkeypatch.setattr(settings, "mail_min_interval_seconds", 0)
    return mailer


def test_every_invitation_of_the_institution_is_cancelled_and_its_link_stops_working(
    app_client, boss, org, mails, test_db_session
):
    client = _as(app_client, "boss")
    pending = f"pendiente@{TEST_EMAIL_DOMAIN}"
    cancelled = f"cancelada@{TEST_EMAIL_DOMAIN}"
    assert _invite(client, org, pending, role="org_admin").status_code == 201
    created = _invite(client, org, cancelled, role="org_admin")  # a reader needs an active admin first: not here
    assert created.status_code == 201
    assert client.post(f"{INVITATIONS_URL}/{created.json()['id']}/cancel").status_code == 204
    link = token_from(mails.sent[0])
    assert client.post(f"{PUBLIC_URL}/details", json={"token": link}).status_code == 200
    assert _invitations_of(test_db_session, org.id) >= 1

    assert _delete(client, org.id).status_code == 204
    assert _invitations_of(test_db_session, org.id) == 0  # the cancelled one too: its history goes with the institution
    assert client.post(f"{PUBLIC_URL}/details", json={"token": link}).status_code == 404


@pytest.mark.parametrize("users", ["unlink", "delete"])
def test_the_invitations_are_cancelled_whatever_happens_to_the_users(
    app_client, boss, org, team, mails, test_db_session, users
):
    client = _as(app_client, "boss")
    assert _invite(client, org, f"pendiente@{TEST_EMAIL_DOMAIN}").status_code == 201
    assert _delete(client, org.id, users).status_code == 204
    assert _invitations_of(test_db_session, org.id) == 0


def test_a_refused_delete_keeps_the_invitations(app_client, boss, org, team, mails, test_db_session):
    client = _as(app_client, "boss")
    assert _invite(client, org, f"pendiente@{TEST_EMAIL_DOMAIN}").status_code == 201
    assert _delete(client, org.id).status_code == 409
    assert _invitations_of(test_db_session, org.id) == 1


# --- unlink ----------------------------------------------------------------------------------------------------------


def test_unlink_sets_every_user_free_and_deletes_the_institution(app_client, boss, org, team, test_db_session):
    assert _delete(_as(app_client, "boss"), org.id, "unlink").status_code == 204
    assert not _org_exists(test_db_session, org.id)
    for name in team:
        user = _user(test_db_session, name)
        assert user is not None and user.organization_id is None and user.role == "viewer"


def test_the_institution_admin_becomes_a_viewer_even_when_it_was_the_only_admin(
    app_client, boss, org, team, test_db_session
):
    # "jefe" is the only admin and there are other users: deleting it one by one would be refused (409), but the whole
    # institution is going away, so nobody is left without an admin.
    assert _delete(_as(app_client, "boss"), org.id, "unlink").status_code == 204
    jefe = _user(test_db_session, "jefe")
    assert jefe.role == "viewer" and jefe.organization_id is None and jefe.is_active is True


def test_unlink_keeps_active_users_active_and_inactive_users_inactive(app_client, boss, org, team, test_db_session):
    assert _delete(_as(app_client, "boss"), org.id, "unlink").status_code == 204
    assert _user(test_db_session, "ana").is_active is True
    assert _user(test_db_session, "dormido").is_active is False


def test_unlink_removes_the_views_the_users_had_and_the_ones_of_the_institution(
    app_client, boss, org, team, test_db_session
):
    permissions.replace_user_radar_views(test_db_session, team["ana"], ["TSTA"], boss)
    ana_id = team["ana"].id
    assert _delete(_as(app_client, "boss"), org.id, "unlink").status_code == 204
    assert test_db_session.query(Permission).filter(Permission.user_id == ana_id).count() == 0
    assert test_db_session.query(Permission).filter(Permission.organization_id == org.id).count() == 0
    assert permissions.stored_radar_views(_user(test_db_session, "ana")) == []


def test_unlink_closes_the_sessions_but_the_accounts_can_log_in_again(app_client, boss, org, team, test_db_session):
    other_browser = _second_client()
    login(other_browser, "ana")
    assert other_browser.get("/api/v1/auth/me").status_code == 200
    assert _delete(_as(app_client, "boss"), org.id, "unlink").status_code == 204
    assert other_browser.get("/api/v1/auth/me").status_code == 401
    assert other_browser.post("/api/v1/auth/refresh").status_code == 401
    other_browser.cookies.clear()
    login(other_browser, "ana")  # the account is alive: a viewer with no institution and no views
    assert other_browser.get("/api/v1/permissions/me").json()["radar_detail_views"] == []


def test_unlink_does_not_touch_other_institutions(app_client, boss, org, team, other_org, make_user, test_db_session):
    make_user(username="otro_jefe", role="org_admin", organization_id=other_org.id)
    make_user(username="otro_lector", organization_id=other_org.id)
    assert _delete(_as(app_client, "boss"), org.id, "unlink").status_code == 204
    assert _org_exists(test_db_session, other_org.id)
    for name in ("otro_jefe", "otro_lector"):
        assert _user(test_db_session, name).organization_id == other_org.id
    assert _user(test_db_session, "otro_jefe").role == "org_admin"
    assert test_db_session.query(Permission).filter(Permission.organization_id == other_org.id).count() == 1


# --- delete -----------------------------------------------------------------------------------------------------------


def test_delete_removes_every_user_and_the_institution(app_client, boss, org, team, test_db_session):
    assert _delete(_as(app_client, "boss"), org.id, "delete").status_code == 204
    assert not _org_exists(test_db_session, org.id)
    for name in team:
        assert _user(test_db_session, name) is None


def test_delete_removes_the_only_admin_too(app_client, boss, org, make_user, test_db_session):
    make_user(username="jefe", role="org_admin", organization_id=org.id)
    make_user(username="lector", organization_id=org.id)
    assert _delete(_as(app_client, "boss"), org.id, "delete").status_code == 204
    assert _user(test_db_session, "jefe") is None and _user(test_db_session, "lector") is None


def test_delete_removes_the_sessions_tokens_and_views_of_the_users(app_client, boss, org, team, test_db_session):
    ana = team["ana"]
    permissions.replace_user_radar_views(test_db_session, ana, ["TSTA"], boss)
    email_tokens.issue_token(test_db_session, ana, "verify_email", timedelta(hours=1))
    login(_second_client(), "ana")  # a session row
    ids = [user.id for user in team.values()]
    assert test_db_session.query(UserSession).filter(UserSession.user_id.in_(ids)).count() >= 1
    assert _delete(_as(app_client, "boss"), org.id, "delete").status_code == 204
    assert test_db_session.query(UserSession).filter(UserSession.user_id.in_(ids)).count() == 0
    assert test_db_session.query(EmailToken).filter(EmailToken.user_id.in_(ids)).count() == 0
    assert test_db_session.query(Permission).filter(Permission.user_id.in_(ids)).count() == 0


def test_delete_frees_the_usernames_and_mails_of_its_users(app_client, boss, org, make_user):
    make_user(username="ana", email=f"ana@{TEST_EMAIL_DOMAIN}", organization_id=org.id)
    assert _delete(_as(app_client, "boss"), org.id, "delete").status_code == 204
    make_user(username="ana", email=f"ana@{TEST_EMAIL_DOMAIN}")  # the same name and mail again: no conflict


def test_delete_closes_the_open_session_of_a_deleted_user_at_once(app_client, boss, org, team):
    other_browser = _second_client()
    login(other_browser, "ana")
    assert _delete(_as(app_client, "boss"), org.id, "delete").status_code == 204
    assert other_browser.get("/api/v1/auth/me").status_code == 401  # the API reads the user on every request


def test_delete_does_not_touch_other_institutions_or_the_general_admin(
    app_client, boss, org, team, other_org, make_user, test_db_session
):
    make_user(username="otro_jefe", role="org_admin", organization_id=other_org.id)
    make_user(username="otro_lector", organization_id=other_org.id)
    client = _as(app_client, "boss")
    assert _delete(client, org.id, "delete").status_code == 204
    assert _org_exists(test_db_session, other_org.id)
    assert _user(test_db_session, "otro_jefe") is not None and _user(test_db_session, "otro_lector") is not None
    assert _user(test_db_session, "boss") is not None
    assert client.get("/api/v1/auth/me").status_code == 200  # the admin's own session is still valid
    assert other_org.name in [o["name"] for o in client.get(ORG_URL).json()]
