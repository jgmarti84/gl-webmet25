# tests/auth/test_invitations_existing_account.py
"""Inviting someone who already has an account.

The inviter (general admin or institution admin) gets a WARNING instead of an error and the mail goes out anyway. The
person opens the link and, because the mail has an account, logs in with it instead of filling the sign-up form; the
account then joins the institution. Everything goes through the real application (`app_client`).

What is checked: which accounts can be invited and by whom (a table of cases), that the page can tell if the mail has
an account (`details`), and that accepting needs BOTH the link and a session of the account of that mail, re-checks the
rules at that moment and leaves the person inside with the new permissions.
"""

import pytest
from fastapi.testclient import TestClient

from api.app.auth import organizations as orgs
from api.app.auth import permissions
from api.app.auth.google import GoogleIdentity
from api.app.config import settings
from radar_db.models import Invitation, Organization, User

from .conftest import TEST_EMAIL_DOMAIN, TEST_PASSWORD, login, token_from

ADMIN_URL = "/api/v1/admin/invitations"
ORG_URL = "/api/v1/org/invitations"
PUBLIC_URL = "/api/v1/invitations"
INVITED = f"invitada@{TEST_EMAIL_DOMAIN}"

pytestmark = pytest.mark.usefixtures("registration_on")


@pytest.fixture(autouse=True)
def _no_wait_between_mails(monkeypatch):
    monkeypatch.setattr(settings, "mail_min_interval_seconds", 0)


@pytest.fixture
def boss(make_user):
    return make_user(username="boss", role="admin")


@pytest.fixture
def org(make_org, make_radar, make_user):
    """The institution of the tests, with its admin ("orgboss"): a viewer can only join an institution that has one."""
    make_radar("TSTA")
    make_radar("TSTB")
    institution = make_org(name="Test Org A", seat_limit=5, views=["TSTA", "TSTB"])
    make_user(username="orgboss", role="org_admin", organization_id=institution.id)
    return institution


@pytest.fixture
def org_boss(org, test_db_session):
    return test_db_session.query(User).filter(User.username == "orgboss").one()


@pytest.fixture
def other_org(make_org, make_user):
    """Another institution, with its own admin (a viewer can only join an institution that has an active admin)."""
    other = make_org(name="Test Org B", seat_limit=5, views=["TSTA"])
    make_user(username="otherboss", role="org_admin", organization_id=other.id)
    return other


def _as(client, username):
    login(client, username)
    return client


def _invite(client, org, **overrides):
    body = {"email": INVITED, "organization_id": org.id, "role": "viewer"}
    body.update(overrides)
    return client.post(ADMIN_URL, json=body)


def _org_invite(client, **overrides):
    return client.post(ORG_URL, json={"email": INVITED, **overrides})


def _details(client, token):
    return client.post(f"{PUBLIC_URL}/details", json={"token": token})


def _accept_existing(client, token, **headers):
    return client.post(f"{PUBLIC_URL}/accept-existing", json={"token": token}, headers=headers)


def _second_client():
    """Another browser: its own cookies, the same application (and the same test database session)."""
    from api.app.main import app

    return TestClient(app, base_url="http://testserver")


def _user(db, username):
    return db.query(User).filter(User.username == username).one()


def _invited_by(client, who, org, mailer, **overrides):
    """Invite INVITED as `who` ("boss" or "orgboss") and return the token of the mail."""
    login(client, who)
    general = who.startswith("boss")  # "boss", "boss2": general admins; anything else is the institution admin
    response = _invite(client, org, **overrides) if general else _org_invite(client, **overrides)
    assert response.status_code == 201, response.text
    client.cookies.clear()
    return token_from(mailer.sent[-1])


# --- inviting: the warning and the table of cases ------------------------------------------------------------------


def test_an_account_without_institution_is_invited_by_the_general_admin_with_a_warning(
    app_client, boss, org, make_user, mailer
):
    make_user(username="ana", email=INVITED)
    response = _invite(_as(app_client, "boss"), org)
    assert response.status_code == 201, response.text
    assert response.json()["existing_account"] is True and response.json()["leaves_organization"] is None
    assert [mail.to for mail in mailer.sent] == [INVITED]


def test_a_mail_without_account_says_so(app_client, boss, org, mailer):
    response = _invite(_as(app_client, "boss"), org)
    assert response.status_code == 201 and response.json()["existing_account"] is False


def test_the_general_admin_can_invite_a_member_of_another_institution_and_is_told_where_it_leaves(
    app_client, boss, org, other_org, make_user, mailer
):
    make_user(username="ana", email=INVITED, organization_id=other_org.id)
    response = _invite(_as(app_client, "boss"), org)
    assert response.status_code == 201, response.text
    assert response.json()["existing_account"] is True and response.json()["leaves_organization"] == other_org.name
    assert [mail.to for mail in mailer.sent] == [INVITED]


def test_the_general_admin_can_invite_an_existing_viewer_as_institution_admin(app_client, boss, org, make_user, mailer):
    make_user(username="ana", email=INVITED)
    response = _invite(_as(app_client, "boss"), org, role="org_admin")
    assert response.status_code == 201 and response.json()["existing_account"] is True


def test_a_company_admin_cannot_take_someone_from_another_institution(
    app_client, org, org_boss, other_org, make_user, mailer, test_db_session
):
    make_user(username="ana", email=INVITED, organization_id=other_org.id)
    response = _org_invite(_as(app_client, "orgboss"))
    assert response.status_code == 409
    assert "administrador general" in response.json()["detail"] and "otra institución" in response.json()["detail"]
    assert not mailer.sent and test_db_session.query(Invitation).count() == 0


@pytest.mark.parametrize("who", ["boss", "orgboss"])
def test_an_account_that_is_already_of_this_institution_is_refused(
    app_client, boss, org, org_boss, make_user, mailer, who
):
    make_user(username="ana", email=INVITED, organization_id=org.id)
    client = _as(app_client, who)
    response = _invite(client, org) if who == "boss" else _org_invite(client)
    assert response.status_code == 409 and "ya pertenece a esta institución" in response.json()["detail"]
    assert not mailer.sent


@pytest.mark.parametrize("who", ["boss", "orgboss"])
def test_an_institution_admin_account_cannot_be_invited(
    app_client, boss, org, org_boss, other_org, make_user, mailer, who
):
    make_user(username="jefa", email=INVITED, role="org_admin", organization_id=other_org.id)
    client = _as(app_client, who)
    response = _invite(client, org) if who == "boss" else _org_invite(client)
    assert response.status_code == 409 and "administradora de una institución" in response.json()["detail"]
    assert not mailer.sent


@pytest.mark.parametrize("who", ["boss", "orgboss"])
def test_a_general_admin_account_cannot_be_invited(app_client, boss, org, org_boss, make_user, mailer, who):
    make_user(username="otro-admin", email=INVITED, role="admin")
    client = _as(app_client, who)
    response = _invite(client, org) if who == "boss" else _org_invite(client)
    assert response.status_code == 409 and "administrador general" in response.json()["detail"]
    assert not mailer.sent


@pytest.mark.parametrize("who", ["boss", "orgboss"])
def test_a_deactivated_account_cannot_be_invited(app_client, boss, org, org_boss, make_user, mailer, who):
    make_user(username="ana", email=INVITED, is_active=False)
    client = _as(app_client, who)
    response = _invite(client, org) if who == "boss" else _org_invite(client)
    assert response.status_code == 409 and "desactivada" in response.json()["detail"]
    assert not mailer.sent


@pytest.mark.parametrize("who", ["boss", "orgboss"])
def test_an_account_that_never_verified_its_mail_cannot_be_invited(
    app_client, boss, org, org_boss, make_user, mailer, who
):
    make_user(username="ana", email=INVITED, email_verified=False)
    client = _as(app_client, who)
    response = _invite(client, org) if who == "boss" else _org_invite(client)
    assert response.status_code == 409 and "verificó su mail" in response.json()["detail"]
    assert not mailer.sent


def test_a_pending_invitation_of_another_institution_still_blocks_an_existing_account(
    app_client, boss, org, other_org, make_user, mailer
):
    make_user(username="ana", email=INVITED)
    client = _as(app_client, "boss")
    assert _invite(client, other_org).status_code == 201
    assert _invite(client, org).status_code == 409
    assert len(mailer.sent) == 1


def test_the_list_works_out_existing_account_when_it_is_asked(app_client, boss, org, make_user, test_db_session):
    client = _as(app_client, "boss")
    assert _invite(client, org).json()["existing_account"] is False
    ana = make_user(username="ana", email=INVITED)  # the person signs up after being invited
    assert client.get(ADMIN_URL).json()[0]["existing_account"] is True
    test_db_session.delete(ana)
    test_db_session.flush()
    assert client.get(ADMIN_URL).json()[0]["existing_account"] is False


def test_the_company_admin_list_shows_it_too(app_client, org, org_boss, make_user):
    make_user(username="ana", email=INVITED)
    client = _as(app_client, "orgboss")
    _org_invite(client)
    assert client.get(ORG_URL).json()[0]["existing_account"] is True


def test_creating_an_institution_can_invite_an_admin_that_already_has_an_account(
    app_client, boss, make_user, mailer, test_db_session
):
    make_user(username="ana", email=INVITED)
    body = {"name": "Test Org Nueva", "seat_limit": 3, "admin": {"mode": "invite", "email": INVITED}}
    response = _as(app_client, "boss").post("/api/v1/admin/organizations", json=body)
    assert response.status_code == 201, response.text
    assert response.json()["invited_admin_has_account"] is True and response.json()["pending_invitations"] == 1
    assert [mail.to for mail in mailer.sent] == [INVITED]
    assert test_db_session.query(Organization).filter(Organization.name == "Test Org Nueva").count() == 1


def test_creating_an_institution_with_a_new_mail_says_there_is_no_account(app_client, boss, mailer):
    body = {"name": "Test Org Nueva", "seat_limit": 3, "admin": {"mode": "invite", "email": INVITED}}
    response = _as(app_client, "boss").post("/api/v1/admin/organizations", json=body)
    assert response.status_code == 201 and response.json()["invited_admin_has_account"] is False


def test_the_default_mail_text_covers_both_cases(app_client, boss, org, mailer):
    _invite(_as(app_client, "boss"), org)
    text = mailer.sent[-1].text
    assert "si todavía no tenés cuenta, la creás" in text and "si ya tenés una, iniciás sesión" in text


# --- the page asks if the mail has an account ----------------------------------------------------------------------


def test_details_say_if_the_mail_has_an_account_and_follow_it_when_it_changes(
    app_client, boss, org, make_user, mailer, test_db_session
):
    token = _invited_by(app_client, "boss", org, mailer)
    assert _details(app_client, token).json()["account_exists"] is False
    ana = make_user(username="ana", email=INVITED)  # signs up by itself before opening the link
    assert _details(app_client, token).json()["account_exists"] is True
    test_db_session.delete(ana)
    test_db_session.flush()
    assert _details(app_client, token).json()["account_exists"] is False


# --- accepting with an existing account ----------------------------------------------------------------------------


def test_accept_existing_needs_a_session_a_valid_link_and_a_local_origin(app_client, boss, org, make_user, mailer):
    make_user(username="ana", email=INVITED)
    token = _invited_by(app_client, "boss", org, mailer)
    assert _accept_existing(app_client, token).status_code == 401  # the link alone does nothing
    login(app_client, "ana")
    assert _accept_existing(app_client, "A" * 43).status_code == 404
    assert _accept_existing(app_client, "corto").status_code == 404
    assert _accept_existing(app_client, token, Origin="https://evil.example").status_code == 403


def test_a_free_viewer_joins_with_the_views_of_the_invitation_and_gets_a_new_session(
    app_client, org, org_boss, make_user, mailer, test_db_session
):
    ana = make_user(username="ana", email=INVITED)
    other_browser = _second_client()
    login(other_browser, "ana")  # an older session of the same person
    token = _invited_by(app_client, "orgboss", org, mailer, radar_views=["TSTA"])
    login(app_client, "ana")
    response = _accept_existing(app_client, token)
    assert response.status_code == 200, response.text
    assert response.json()["username"] == "ana" and response.json()["role"] == "viewer"
    test_db_session.refresh(ana)
    assert ana.organization_id == org.id and permissions.stored_radar_views(ana) == ["TSTA"]
    assert test_db_session.query(Invitation).filter(Invitation.email == INVITED).one().accepted_at is not None
    assert app_client.get("/api/v1/auth/me").status_code == 200  # the new session works
    assert other_browser.get("/api/v1/auth/me").status_code == 401  # the old ones were closed


def test_without_a_list_the_viewer_gets_a_copy_of_the_institution_views(
    app_client, org, org_boss, make_user, mailer, test_db_session
):
    ana = make_user(username="ana", email=INVITED)
    token = _invited_by(app_client, "orgboss", org, mailer)
    login(app_client, "ana")
    assert _accept_existing(app_client, token).status_code == 200
    test_db_session.refresh(ana)
    assert permissions.stored_radar_views(ana) == ["TSTA", "TSTB"]


def test_the_views_it_had_before_are_replaced(app_client, org, org_boss, make_user, mailer, test_db_session):
    ana = make_user(username="ana", email=INVITED)
    permissions.replace_user_radar_views(test_db_session, ana, ["TSTB"], org_boss)
    token = _invited_by(app_client, "orgboss", org, mailer, radar_views=["TSTA"])
    login(app_client, "ana")
    assert _accept_existing(app_client, token).status_code == 200
    test_db_session.refresh(ana)
    assert permissions.stored_radar_views(ana) == ["TSTA"]


def test_invited_as_institution_admin_the_account_becomes_its_admin(
    app_client, boss, org, make_user, mailer, test_db_session
):
    ana = make_user(username="ana", email=INVITED)
    token = _invited_by(app_client, "boss", org, mailer, role="org_admin")
    login(app_client, "ana")
    assert _accept_existing(app_client, token).json()["role"] == "org_admin"
    test_db_session.refresh(ana)
    assert ana.role == "org_admin" and ana.organization_id == org.id
    assert app_client.get("/api/v1/org").status_code == 200  # it can use the institution panel now


def test_a_member_of_another_institution_invited_by_the_general_admin_moves(
    app_client, boss, org, org_boss, other_org, make_user, mailer, test_db_session
):
    ana = make_user(username="ana", email=INVITED, organization_id=other_org.id)
    permissions.replace_user_radar_views(test_db_session, ana, ["TSTA"], boss)
    old_seats, new_seats = orgs.seats_used(test_db_session, other_org), orgs.seats_used(test_db_session, org)
    token = _invited_by(app_client, "boss", org, mailer, radar_views=["TSTB"])
    login(app_client, "ana")
    assert _accept_existing(app_client, token).status_code == 200
    test_db_session.refresh(ana)
    assert ana.organization_id == org.id and permissions.stored_radar_views(ana) == ["TSTB"]
    assert orgs.seats_used(test_db_session, other_org) == old_seats - 1  # it left the old one: its seat is free
    assert orgs.seats_used(test_db_session, org) == new_seats + 1


def test_a_company_admin_invitation_cannot_take_someone_who_joined_another_institution_meanwhile(
    app_client, org, org_boss, other_org, make_user, mailer, test_db_session
):
    ana = make_user(username="ana", email=INVITED)
    token = _invited_by(app_client, "orgboss", org, mailer)  # it had no institution when it was invited
    ana.organization_id = other_org.id  # ... and joined another one before opening the link
    test_db_session.flush()
    login(app_client, "ana")
    response = _accept_existing(app_client, token)
    assert response.status_code == 409 and "administrador general" in response.json()["detail"]
    test_db_session.refresh(ana)
    assert ana.organization_id == other_org.id


def test_if_the_inviter_no_longer_exists_it_cannot_take_someone_from_another_institution(
    app_client, boss, org, org_boss, other_org, make_user, mailer, test_db_session
):
    second = make_user(username="boss2", role="admin")
    ana = make_user(username="ana", email=INVITED, organization_id=other_org.id)
    token = _invited_by(app_client, "boss2", org, mailer)
    test_db_session.query(User).filter(User.id == second.id).delete(synchronize_session=False)  # as when it is deleted
    test_db_session.expire_all()
    login(app_client, "ana")
    assert _accept_existing(app_client, token).status_code == 409  # unknown inviter: the most restrictive rule
    test_db_session.refresh(ana)
    assert ana.organization_id == other_org.id


def test_a_session_of_another_account_cannot_accept_and_changes_nothing(
    app_client, org, org_boss, make_user, mailer, test_db_session
):
    ana = make_user(username="ana", email=INVITED)
    make_user(username="intruso", email=f"intruso@{TEST_EMAIL_DOMAIN}")
    token = _invited_by(app_client, "orgboss", org, mailer)
    login(app_client, "intruso")
    response = _accept_existing(app_client, token)
    assert response.status_code == 403 and "otra cuenta" in response.json()["detail"]
    assert INVITED not in response.text  # the mail is not shown
    test_db_session.refresh(ana)
    assert ana.organization_id is None
    assert test_db_session.query(Invitation).filter(Invitation.email == INVITED).one().accepted_at is None
    login(app_client, "ana")
    assert _accept_existing(app_client, token).status_code == 200  # the right account still can


def test_the_rules_are_checked_again_when_accepting(app_client, org, org_boss, make_user, mailer, test_db_session):
    ana = make_user(username="ana", email=INVITED)
    token = _invited_by(app_client, "orgboss", org, mailer)
    login(app_client, "ana")
    org.is_active = False
    test_db_session.flush()
    assert _accept_existing(app_client, token).status_code == 409  # the institution was deactivated
    org.is_active = True
    org_boss.is_active = False
    test_db_session.flush()
    assert _accept_existing(app_client, token).status_code == 409  # a viewer needs an active admin
    org_boss.is_active = True
    for name in ("usr1", "usr2", "usr3", "usr4"):  # fill the institution behind the reservation's back
        make_user(username=name, organization_id=org.id)
    test_db_session.flush()
    assert _accept_existing(app_client, token).status_code == 409  # no free seat
    test_db_session.refresh(ana)
    assert ana.organization_id is None


def test_an_account_that_joined_this_institution_meanwhile_gets_a_409(
    app_client, boss, org, org_boss, make_user, mailer, test_db_session
):
    ana = make_user(username="ana", email=INVITED)
    token = _invited_by(app_client, "boss", org, mailer)
    ana.organization_id = org.id
    test_db_session.flush()
    login(app_client, "ana")
    assert _accept_existing(app_client, token).status_code == 409


def test_the_link_works_once(app_client, org, org_boss, make_user, mailer):
    make_user(username="ana", email=INVITED)
    token = _invited_by(app_client, "orgboss", org, mailer)
    login(app_client, "ana")
    assert _accept_existing(app_client, token).status_code == 200
    assert _accept_existing(app_client, token).status_code == 404
    assert _details(app_client, token).status_code == 404


def test_signing_in_with_google_and_then_accepting_works_too(
    app_client, org, org_boss, make_user, mailer, google_on, google_verifier
):
    make_user(username="ana", email=INVITED, google_sub="g-1")
    token = _invited_by(app_client, "orgboss", org, mailer)
    google_verifier.identity = GoogleIdentity(sub="g-1", email=INVITED, email_verified=True, name="Ana")
    assert app_client.post("/api/v1/auth/google", json={"credential": "x"}).status_code == 200
    assert _accept_existing(app_client, token).status_code == 200


def test_the_sign_up_ways_still_refuse_a_mail_that_has_an_account(
    app_client, boss, org, make_user, mailer, google_on, google_verifier
):
    make_user(username="ana", email=INVITED)
    token = _invited_by(app_client, "boss", org, mailer)
    form = {"token": token, "username": "nueva", "password": TEST_PASSWORD, "accept_terms": True}
    assert app_client.post(f"{PUBLIC_URL}/accept", json=form).status_code == 409
    google_verifier.identity = GoogleIdentity(sub="g-9", email=INVITED, email_verified=True, name="Otra")
    assert app_client.post(f"{PUBLIC_URL}/accept-google", json={"token": token, "credential": "x"}).status_code == 409
