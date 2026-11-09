# tests/auth/test_user_delete.py
"""Deleting users (spec G): the general admin deletes another user, and every person deletes their own account.

Everything goes through the real application (`app_client`). What is checked here:

* only the general admin can delete OTHER users (401 without a session, 403 for institution admins and viewers);
* the delete is real: the account, its sessions, tokens and own views are gone, what it granted or invited stays (the
  "who" becomes empty), the name and the mail are free again, and its open session stops working at once;
* the rules: an institution never ends with active users and no active admin, a general admin cannot delete itself, and
  the profile endpoint only ever acts on the account of the session (it takes no id);
* a deleted member gives its seat back, and the institution itself is never touched.
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from api.app.auth import email_tokens, permissions
from api.app.auth import organizations as orgs
from api.app.auth.cookies import access_cookie_name, refresh_cookie_name
from api.app.auth.google import GoogleIdentity
from api.app.config import settings
from radar_db.models import EmailToken, Invitation, Organization, Permission, User, UserSession

from .conftest import TEST_EMAIL_DOMAIN, TEST_PASSWORD, login, token_from

ADMIN_URL = "/api/v1/admin/users"
PROFILE_URL = "/api/v1/profile"
DOMAIN = TEST_EMAIL_DOMAIN


@pytest.fixture
def boss(make_user):
    return make_user(username="boss", role="admin")


@pytest.fixture
def org(make_org, make_radar):
    make_radar("TSTA")
    return make_org(seat_limit=5, views=["TSTA"])


def _as(client, username):
    login(client, username)
    return client


def _delete(client, user_id):
    return client.delete(f"{ADMIN_URL}/{user_id}")


def _exists(db, username):
    return db.query(User).filter(User.username == username).count() == 1


def _second_client(app_client):
    """Another browser: its own cookies, the same application (and the same test database session)."""
    from api.app.main import app

    return TestClient(app, base_url="http://testserver")


def _set_cookie_header(response, cookie_name):
    return next(c for c in response.headers.get_list("set-cookie") if c.startswith(f"{cookie_name}="))


# --- who may use it -------------------------------------------------------------------------------------------


@pytest.mark.parametrize("method,path", [("delete", f"{ADMIN_URL}/1"), ("delete", PROFILE_URL)])
def test_without_a_session_it_is_401(app_client, method, path):
    assert app_client.request(method, path).status_code == 401


@pytest.mark.parametrize("who", ["org_admin", "viewer"])
def test_only_the_general_admin_deletes_other_users(app_client, make_user, org, test_db_session, who):
    make_user(username="jefe", role="org_admin", organization_id=org.id)
    target = make_user(username="victima", organization_id=org.id)
    if who == "viewer":
        make_user(username="otro", organization_id=org.id)
    login(app_client, "jefe" if who == "org_admin" else "otro")
    assert _delete(app_client, target.id).status_code == 403
    assert _exists(test_db_session, "victima")


def test_a_foreign_origin_is_refused_on_both_endpoints(app_client, boss, make_user, test_db_session):
    target = make_user(username="victima")
    login(app_client, "boss")
    evil = {"Origin": "https://evil.example"}
    assert app_client.delete(f"{ADMIN_URL}/{target.id}", headers=evil).status_code == 403
    login(app_client, "victima")
    assert app_client.delete(PROFILE_URL, headers=evil).status_code == 403
    assert _exists(test_db_session, "victima") and _exists(test_db_session, "boss")


def test_an_unknown_id_is_404_and_a_bad_id_is_422(app_client, boss):
    client = _as(app_client, "boss")
    assert _delete(client, 999999999).status_code == 404
    assert client.delete(f"{ADMIN_URL}/abc").status_code == 422
    assert client.delete(f"{ADMIN_URL}/1;DROP TABLE users").status_code == 422


# --- the general admin deletes a user ---------------------------------------------------------------------------


def test_the_admin_deletes_a_viewer(app_client, boss, make_user, test_db_session):
    target = make_user(username="victima", email=f"victima@{DOMAIN}")
    client = _as(app_client, "boss")
    assert _delete(client, target.id).status_code == 204
    assert not _exists(test_db_session, "victima")
    assert "victima" not in [u["username"] for u in client.get(ADMIN_URL).json()]
    assert _delete(client, target.id).status_code == 404  # already gone


def test_the_deleted_user_cannot_log_in_and_its_open_session_dies_at_once(app_client, boss, make_user):
    target = make_user(username="victima")
    other_browser = _second_client(app_client)
    login(other_browser, "victima")
    assert other_browser.get("/api/v1/auth/me").status_code == 200
    assert _delete(_as(app_client, "boss"), target.id).status_code == 204
    assert other_browser.get("/api/v1/auth/me").status_code == 401  # the API reads the user on every request
    assert other_browser.post("/api/v1/auth/refresh").status_code == 401
    other_browser.cookies.clear()
    assert (
        other_browser.post("/api/v1/auth/login", json={"username": "victima", "password": TEST_PASSWORD}).status_code
        == 401
    )


def test_the_account_its_sessions_tokens_and_own_views_are_deleted(app_client, boss, make_user, org, test_db_session):
    target = make_user(username="victima", organization_id=org.id)
    permissions.replace_user_radar_views(test_db_session, target, ["TSTA"], boss)
    email_tokens.issue_token(test_db_session, target, "verify_email", timedelta(hours=1))
    login(_second_client(app_client), "victima")  # a session row
    uid = target.id
    assert test_db_session.query(UserSession).filter(UserSession.user_id == uid).count() >= 1
    assert _delete(_as(app_client, "boss"), uid).status_code == 204
    assert test_db_session.query(UserSession).filter(UserSession.user_id == uid).count() == 0
    assert test_db_session.query(EmailToken).filter(EmailToken.user_id == uid).count() == 0
    assert test_db_session.query(Permission).filter(Permission.user_id == uid).count() == 0


def test_what_the_user_granted_or_invited_stays_with_the_who_empty(
    app_client, boss, make_user, org, mailer, registration_on, test_db_session, monkeypatch
):
    monkeypatch.setattr(settings, "mail_min_interval_seconds", 0)
    second = make_user(username="boss2", role="admin")
    ana = make_user(username="ana", organization_id=org.id)
    permissions.replace_user_radar_views(test_db_session, ana, ["TSTA"], second)  # boss2 granted these views
    login(app_client, "boss2")
    body = {"email": f"nuevo@{DOMAIN}", "organization_id": org.id, "role": "org_admin"}
    assert app_client.post("/api/v1/admin/invitations", json=body).status_code == 201  # boss2 invited this person
    assert _delete(_as(app_client, "boss"), second.id).status_code == 204
    test_db_session.expire_all()  # the database changed these rows (SET NULL), not the session
    granted = test_db_session.query(Permission).filter(Permission.user_id == ana.id).one()
    assert granted.resource == "TSTA" and granted.granted_by is None  # the view stays, nobody to blame
    invitation = test_db_session.query(Invitation).filter(Invitation.email == f"nuevo@{DOMAIN}").one()
    assert invitation.invited_by is None and invitation.accepted_at is None and invitation.cancelled_at is None


def test_the_name_and_the_mail_are_free_again_and_the_person_can_be_invited(
    app_client, boss, make_user, make_org, mailer, registration_on, monkeypatch
):
    monkeypatch.setattr(settings, "mail_min_interval_seconds", 0)
    target = make_user(username="victima", email=f"victima@{DOMAIN}")
    client = _as(app_client, "boss")
    assert _delete(client, target.id).status_code == 204
    make_user(username="victima", email=f"victima@{DOMAIN}")  # the same name and mail again: no conflict
    org = make_org(name="Test Org Libre")
    body = {"email": f"otra.persona@{DOMAIN}", "organization_id": org.id, "role": "org_admin"}
    assert client.post("/api/v1/admin/invitations", json=body).status_code == 201


def test_a_deleted_google_link_frees_that_google_account(
    app_client, boss, make_user, org, mailer, registration_on, google_on, google_verifier, monkeypatch
):
    monkeypatch.setattr(settings, "mail_min_interval_seconds", 0)
    target = make_user(username="victima", email=f"victima@{DOMAIN}", google_sub="g-77")
    client = _as(app_client, "boss")
    body = {"email": f"nueva@{DOMAIN}", "organization_id": org.id, "role": "org_admin"}
    assert client.post("/api/v1/admin/invitations", json=body).status_code == 201
    token = token_from(mailer.sent[-1])
    google_verifier.identity = GoogleIdentity(sub="g-77", email=f"nueva@{DOMAIN}", email_verified=True, name="Nueva")
    refused = client.post("/api/v1/invitations/accept-google", json={"token": token, "credential": "x"})
    assert refused.status_code == 409  # still linked to the user
    assert _delete(client, target.id).status_code == 204
    accepted = client.post("/api/v1/invitations/accept-google", json={"token": token, "credential": "x"})
    assert accepted.status_code == 200  # the Google account is free now


# --- seats and the institution ----------------------------------------------------------------------------------


def test_deleting_an_active_member_gives_its_seat_back_and_an_inactive_one_changes_nothing(
    app_client, boss, make_user, org, test_db_session
):
    make_user(username="jefe", role="org_admin", organization_id=org.id)
    active = make_user(username="activo", organization_id=org.id)
    sleeping = make_user(username="dormido", organization_id=org.id, is_active=False)
    client = _as(app_client, "boss")
    before = orgs.seats_used(test_db_session, org)
    assert _delete(client, sleeping.id).status_code == 204
    assert orgs.seats_used(test_db_session, org) == before
    assert _delete(client, active.id).status_code == 204
    assert orgs.seats_used(test_db_session, org) == before - 1


def test_the_institution_stays_whatever_happens_to_its_users(app_client, boss, make_user, org, test_db_session):
    only = make_user(username="unico", organization_id=org.id)
    assert _delete(_as(app_client, "boss"), only.id).status_code == 204
    kept = test_db_session.get(Organization, org.id)
    assert kept is not None and kept.is_active is True


# --- the institution admin ---------------------------------------------------------------------------------------


def test_the_only_active_admin_of_an_institution_with_other_users_cannot_be_deleted(
    app_client, boss, make_user, org, test_db_session
):
    jefe = make_user(username="jefe", role="org_admin", organization_id=org.id)
    make_user(username="lector", organization_id=org.id)
    response = _delete(_as(app_client, "boss"), jefe.id)
    assert response.status_code == 409
    assert "administrador" in response.json()["detail"] and org.name in response.json()["detail"]
    assert _exists(test_db_session, "jefe")
    # ... nor can the admin delete its own account.
    login(app_client, "jefe")
    self_delete = app_client.delete(PROFILE_URL)
    assert self_delete.status_code == 409 and "administrador" in self_delete.json()["detail"]
    assert _exists(test_db_session, "jefe")


def test_an_institution_admin_can_be_deleted_when_there_is_another_active_admin(
    app_client, boss, make_user, org, test_db_session
):
    first = make_user(username="jefe1", role="org_admin", organization_id=org.id)
    make_user(username="jefe2", role="org_admin", organization_id=org.id)
    make_user(username="lector", organization_id=org.id)
    assert _delete(_as(app_client, "boss"), first.id).status_code == 204
    assert not _exists(test_db_session, "jefe1")


def test_two_admins_cannot_leave_the_institution_without_admin_one_after_the_other(
    app_client, make_user, org, test_db_session
):
    make_user(username="jefe1", role="org_admin", organization_id=org.id)
    make_user(username="jefe2", role="org_admin", organization_id=org.id)
    make_user(username="lector", organization_id=org.id)
    login(app_client, "jefe1")
    assert app_client.delete(PROFILE_URL).status_code == 204  # jefe2 is still there
    login(app_client, "jefe2")
    assert app_client.delete(PROFILE_URL).status_code == 409  # now it would leave "lector" without an admin
    assert _exists(test_db_session, "jefe2") and _exists(test_db_session, "lector")


def test_the_only_user_of_an_institution_can_be_deleted_even_if_it_is_the_admin(
    app_client, boss, make_user, org, test_db_session
):
    jefe = make_user(username="jefe", role="org_admin", organization_id=org.id)
    assert _delete(_as(app_client, "boss"), jefe.id).status_code == 204
    assert not _exists(test_db_session, "jefe")
    assert test_db_session.get(Organization, org.id) is not None  # an empty institution without admin is valid


def test_an_inactive_institution_admin_can_be_deleted_even_if_there_are_other_users(
    app_client, boss, make_user, org, test_db_session
):
    sleeping = make_user(username="jefe", role="org_admin", organization_id=org.id, is_active=False)
    make_user(
        username="lector", organization_id=org.id
    )  # active, and no active admin: it does not matter, jefe is inactive
    assert _delete(_as(app_client, "boss"), sleeping.id).status_code == 204
    assert not _exists(test_db_session, "jefe")


def test_a_pending_admin_invitation_does_not_count_as_an_admin(
    app_client, boss, make_user, org, mailer, registration_on, monkeypatch
):
    monkeypatch.setattr(settings, "mail_min_interval_seconds", 0)
    jefe = make_user(username="jefe", role="org_admin", organization_id=org.id)
    make_user(username="lector", organization_id=org.id)
    client = _as(app_client, "boss")
    body = {"email": f"otro.jefe@{DOMAIN}", "organization_id": org.id, "role": "org_admin"}
    assert client.post("/api/v1/admin/invitations", json=body).status_code == 201
    assert _delete(client, jefe.id).status_code == 409  # an invitation that nobody accepted is not an admin


# --- the general admin ------------------------------------------------------------------------------------------


def test_a_general_admin_cannot_delete_its_own_account(app_client, boss, make_user, test_db_session):
    make_user(username="boss2", role="admin")
    client = _as(app_client, "boss")
    by_id = _delete(client, boss.id)
    by_profile = client.delete(PROFILE_URL)
    for response in (by_id, by_profile):
        assert response.status_code == 403 and "administrador general" in response.json()["detail"]
    assert _exists(test_db_session, "boss")


def test_a_general_admin_can_delete_another_general_admin(app_client, boss, make_user, test_db_session):
    other = make_user(username="boss2", role="admin")
    assert _delete(_as(app_client, "boss"), other.id).status_code == 204
    assert not _exists(test_db_session, "boss2") and _exists(test_db_session, "boss")


def test_an_inactive_general_admin_can_be_deleted(app_client, boss, make_user, test_db_session):
    sleeping = make_user(username="boss2", role="admin", is_active=False)
    assert _delete(_as(app_client, "boss"), sleeping.id).status_code == 204


# --- every person deletes its own account ------------------------------------------------------------------------


def test_a_viewer_deletes_its_own_account_and_the_cookies_are_cleared(app_client, make_user, test_db_session):
    make_user(username="ana", email=f"ana@{DOMAIN}")
    login(app_client, "ana")
    response = app_client.delete(PROFILE_URL)
    assert response.status_code == 204
    for name in (access_cookie_name(), refresh_cookie_name()):
        assert "max-age=0" in _set_cookie_header(response, name).lower()
    assert not _exists(test_db_session, "ana")
    assert app_client.get("/api/v1/auth/me").status_code == 401
    assert app_client.post("/api/v1/auth/refresh").status_code == 401


def test_a_member_deleting_its_own_account_gives_its_seat_back(app_client, make_user, org, test_db_session):
    make_user(username="jefe", role="org_admin", organization_id=org.id)
    make_user(username="ana", organization_id=org.id)
    before = orgs.seats_used(test_db_session, org)
    login(app_client, "ana")
    assert app_client.delete(PROFILE_URL).status_code == 204
    assert orgs.seats_used(test_db_session, org) == before - 1


def test_the_profile_endpoint_only_ever_deletes_the_account_of_the_session(app_client, make_user, test_db_session):
    make_user(username="ana")
    victim = make_user(username="victima")
    login(app_client, "ana")
    # An id in the query, in a JSON body or in a header changes nothing: the endpoint takes no id.
    response = app_client.request(
        "DELETE",
        f"{PROFILE_URL}?id={victim.id}&user_id={victim.id}",
        json={"id": victim.id, "user_id": victim.id, "username": "victima"},
        headers={"X-User-Id": str(victim.id)},
    )
    assert response.status_code == 204
    assert not _exists(test_db_session, "ana")
    assert _exists(test_db_session, "victima")


def test_a_deleted_account_cannot_delete_again(app_client, make_user):
    make_user(username="ana")
    login(app_client, "ana")
    assert app_client.delete(PROFILE_URL).status_code == 204
    assert app_client.delete(PROFILE_URL).status_code == 401
