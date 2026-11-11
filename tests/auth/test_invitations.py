# tests/auth/test_invitations.py
"""Invitations by mail (spec E): the general admin invites a company admin, a company admin invites a viewer.

The person opens the link, fills a form or uses Google, and gets an account inside the institution. Everything goes
through the real application (`app_client`), the way the browser uses it; Google and the mail are the fakes of conftest.
Rules checked here: who may invite, the mail already in use, the seat that a pending invitation reserves, the single
use and the expiry of the link, the views the viewer starts with, and that Google must bring the invited mail.
"""

from datetime import datetime, timedelta, timezone

import pytest

from api.app.auth import permissions as perms
from api.app.auth.google import GoogleIdentity
from api.app.config import settings
from radar_db.models import Invitation, User

from .conftest import TEST_EMAIL_DOMAIN, TEST_PASSWORD, login, token_from

ADMIN_URL = "/api/v1/admin/invitations"
ORG_URL = "/api/v1/org/invitations"
PUBLIC_URL = "/api/v1/invitations"
INVITED = f"invitado@{TEST_EMAIL_DOMAIN}"
NEW_PASSWORD = "otra-contrasena-larga"

pytestmark = pytest.mark.usefixtures("registration_on")


@pytest.fixture(autouse=True)
def _no_wait_between_mails(monkeypatch):
    """The minimum time between two mails to one address is checked by its own test."""
    monkeypatch.setattr(settings, "mail_min_interval_seconds", 0)


@pytest.fixture
def boss(make_user):
    return make_user(username="boss", role="admin")


@pytest.fixture
def org(make_org, make_radar):
    make_radar("TSTA")
    make_radar("TSTB")
    return make_org(seat_limit=5, views=["TSTA", "TSTB"])


@pytest.fixture
def org_boss(make_user, org):
    """The company admin: an active admin the company needs before it can have viewers."""
    return make_user(username="orgboss", role="org_admin", organization_id=org.id)


def _as(client, username):
    login(client, username)
    return client


def _invite(client, org, **overrides):
    """POST the admin's invitation; the body is valid unless a test overrides a field."""
    body = {"email": INVITED, "organization_id": org.id, "role": "org_admin"}
    body.update(overrides)
    return client.post(ADMIN_URL, json=body)


def _org_invite(client, **overrides):
    body = {"email": INVITED}
    body.update(overrides)
    return client.post(ORG_URL, json=body)


def _details(client, token):
    return client.post(f"{PUBLIC_URL}/details", json={"token": token})


def _accept(client, token, **overrides):
    body = {"token": token, "username": "nuevo", "password": TEST_PASSWORD, "accept_terms": True}
    body.update(overrides)
    return client.post(f"{PUBLIC_URL}/accept", json=body)


def _accept_google(client, google_verifier, token, identity=None):
    google_verifier.identity = identity or GoogleIdentity(
        sub="g-500", email=INVITED, email_verified=True, name="Invitada Pérez"
    )
    return client.post(f"{PUBLIC_URL}/accept-google", json={"token": token, "credential": "any-token"})


def _invitation(db, email=INVITED):
    return db.query(Invitation).filter(Invitation.email == email).order_by(Invitation.created_at.desc()).first()


def _user(db, username):
    return db.query(User).filter(User.username == username).one()


# --- the general admin invites a company admin ---------------------------------------------------------------


def test_the_admin_invites_a_company_admin_and_a_mail_goes_out(app_client, boss, org, mailer):
    response = _invite(_as(app_client, "boss"), org)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == INVITED and body["role"] == "org_admin"
    assert body["organization_id"] == org.id and body["organization_name"] == org.name
    assert body["radar_views"] is None
    assert body["id"] and body["created_at"] and body["expires_at"]
    assert [mail.to for mail in mailer.sent] == [INVITED]
    mail = mailer.sent[0]
    assert org.name in mail.subject
    assert f"https://webmet.test/invitacion#token={token_from(mail)}" in mail.text


def test_the_answer_never_carries_the_token(app_client, boss, org, mailer):
    body = _invite(_as(app_client, "boss"), org).json()
    token = token_from(mailer.sent[0])
    assert token not in str(body)
    assert "token" not in body and "token_hash" not in body


def test_only_the_hash_of_the_token_is_stored(app_client, boss, org, mailer, test_db_session):
    from api.app.auth.email_tokens import hash_token

    _invite(_as(app_client, "boss"), org)
    token = token_from(mailer.sent[0])
    assert _invitation(test_db_session).token_hash == hash_token(token)


def test_the_invitation_expires_after_the_configured_days(app_client, boss, org, test_db_session, monkeypatch):
    monkeypatch.setattr(settings, "invitation_ttl_days", 3)
    _invite(_as(app_client, "boss"), org)
    invitation = _invitation(test_db_session)
    left = invitation.expires_at - invitation.created_at
    assert timedelta(days=3) - timedelta(minutes=1) <= left <= timedelta(days=3) + timedelta(minutes=1)


def test_the_default_lifetime_is_seven_days(app_client, boss, org, test_db_session):
    _invite(_as(app_client, "boss"), org)
    invitation = _invitation(test_db_session)
    assert abs((invitation.expires_at - invitation.created_at) - timedelta(days=7)) < timedelta(minutes=1)


def test_the_mail_is_stored_normalized(app_client, boss, org, test_db_session):
    response = _invite(_as(app_client, "boss"), org, email=f"  Invitado@{TEST_EMAIL_DOMAIN.upper()} ")
    assert response.status_code == 201
    assert response.json()["email"] == INVITED
    assert _invitation(test_db_session).email == INVITED


def test_invitations_work_with_the_public_registration_off(app_client, boss, org, mailer, monkeypatch):
    monkeypatch.setattr(settings, "registration_enabled", False)
    assert _invite(_as(app_client, "boss"), org).status_code == 201
    assert _accept(app_client, token_from(mailer.sent[0])).status_code == 200


def test_without_the_mail_configured_it_is_503_and_nothing_is_stored(
    app_client, boss, org, test_db_session, monkeypatch
):
    monkeypatch.setattr(settings, "mail_host", "")
    response = _invite(_as(app_client, "boss"), org)
    assert response.status_code == 503
    assert test_db_session.query(Invitation).count() == 0


def test_a_mail_that_already_has_an_account_is_invited_with_a_warning(
    app_client, boss, org, make_user, mailer, test_db_session
):
    # Not an error any more. The invitation is made, the mail goes out and the answer says the account exists.
    make_user(username="yaexiste", email=INVITED)
    response = _invite(_as(app_client, "boss"), org)
    assert response.status_code == 201 and response.json()["existing_account"] is True
    assert [mail.to for mail in mailer.sent] == [INVITED]
    assert test_db_session.query(Invitation).count() == 1


def test_a_pending_invitation_of_another_company_is_409(app_client, boss, org, make_org, mailer):
    other = make_org(name="Test Org B")
    client = _as(app_client, "boss")
    assert _invite(client, other).status_code == 201
    assert _invite(client, org).status_code == 409
    assert len(mailer.sent) == 1


def test_inviting_again_to_the_same_company_replaces_the_old_link(app_client, boss, org, mailer):
    client = _as(app_client, "boss")
    assert _invite(client, org).status_code == 201
    assert _invite(client, org).status_code == 201
    old, new = (token_from(mail) for mail in mailer.sent)
    assert _details(client, old).status_code == 404
    assert _details(client, new).status_code == 200
    assert len(client.get(ADMIN_URL).json()) == 1


def test_an_inactive_company_is_409(app_client, boss, make_org):
    closed = make_org(name="Test Org B", is_active=False)
    assert _invite(_as(app_client, "boss"), closed).status_code == 409


def test_an_unknown_company_is_404(app_client, boss, org):
    assert _invite(_as(app_client, "boss"), org, organization_id=999999999).status_code == 404


def test_a_viewer_needs_an_active_admin_in_the_company(app_client, boss, org, make_user, make_radar):
    client = _as(app_client, "boss")
    assert _invite(client, org, role="viewer").status_code == 409  # the company has nobody yet
    make_user(username="orgboss", role="org_admin", organization_id=org.id)
    assert _invite(client, org, role="viewer").status_code == 201
    # The general admin is not held to the institution's list (only an institution admin is).
    make_radar("TSTC")
    other = f"otro@{TEST_EMAIL_DOMAIN}"
    assert _invite(client, org, role="viewer", email=other, radar_views=["TSTC"]).status_code == 201


def test_a_pending_admin_invitation_does_not_count_as_an_admin(app_client, boss, org):
    client = _as(app_client, "boss")
    assert _invite(client, org, email=f"jefe@{TEST_EMAIL_DOMAIN}").status_code == 201
    assert _invite(client, org, role="viewer").status_code == 409


@pytest.mark.parametrize("bad", [{"role": "admin"}, {"role": "otro"}, {"email": "no-es-un-mail"}, {"email": ""}])
def test_invalid_bodies_are_422(app_client, boss, org, mailer, bad):
    assert _invite(_as(app_client, "boss"), org, **bad).status_code == 422
    assert not mailer.sent


def test_an_unknown_radar_in_the_views_is_422(app_client, boss, org, make_user):
    make_user(username="orgboss", role="org_admin", organization_id=org.id)
    response = _invite(_as(app_client, "boss"), org, role="viewer", radar_views=["NOEXISTE"])
    assert response.status_code == 422


# --- seats: a pending invitation reserves one ----------------------------------------------------------------


def test_a_pending_invitation_takes_a_seat_and_cancelling_gives_it_back(app_client, boss, make_org, make_user):
    small = make_org(name="Test Org B", seat_limit=2)
    make_user(username="orgboss", role="org_admin", organization_id=small.id)  # 1 of 2
    client = _as(app_client, "boss")
    first = _invite(client, small, role="viewer", email=f"uno@{TEST_EMAIL_DOMAIN}")
    assert first.status_code == 201  # the last free seat is now reserved
    assert _invite(client, small, role="viewer", email=f"dos@{TEST_EMAIL_DOMAIN}").status_code == 409
    assert client.post(f"{ADMIN_URL}/{first.json()['id']}/cancel").status_code == 204
    assert _invite(client, small, role="viewer", email=f"dos@{TEST_EMAIL_DOMAIN}").status_code == 201


def test_the_company_reports_its_pending_invitations(app_client, boss, org, org_boss):
    client = _as(app_client, "boss")
    _invite(client, org, role="viewer")
    listed = {o["id"]: o for o in client.get("/api/v1/admin/organizations").json()}
    assert listed[org.id]["pending_invitations"] == 1
    assert listed[org.id]["seats_used"] == 1  # the invitation is reserved, not used
    own = _as(app_client, "orgboss").get("/api/v1/org").json()
    assert own["pending_invitations"] == 1 and own["seats_used"] == 1


def test_an_expired_invitation_gives_its_seat_back(app_client, boss, make_org, make_user, test_db_session):
    small = make_org(name="Test Org B", seat_limit=2)
    make_user(username="orgboss", role="org_admin", organization_id=small.id)
    client = _as(app_client, "boss")
    assert _invite(client, small, role="viewer", email=f"uno@{TEST_EMAIL_DOMAIN}").status_code == 201
    _invitation(test_db_session, f"uno@{TEST_EMAIL_DOMAIN}").expires_at = datetime.now(timezone.utc) - timedelta(
        minutes=1
    )
    test_db_session.flush()
    assert _invite(client, small, role="viewer", email=f"dos@{TEST_EMAIL_DOMAIN}").status_code == 201


# --- the list, cancel and resend -----------------------------------------------------------------------------


def test_the_list_shows_only_pending_invitations(app_client, boss, org, org_boss, test_db_session):
    client = _as(app_client, "boss")
    kept = _invite(client, org, role="viewer", email=f"uno@{TEST_EMAIL_DOMAIN}").json()
    cancelled = _invite(client, org, role="viewer", email=f"dos@{TEST_EMAIL_DOMAIN}").json()
    expired = _invite(client, org, role="viewer", email=f"tres@{TEST_EMAIL_DOMAIN}").json()
    client.post(f"{ADMIN_URL}/{cancelled['id']}/cancel")
    _invitation(test_db_session, f"tres@{TEST_EMAIL_DOMAIN}").expires_at = datetime.now(timezone.utc) - timedelta(
        minutes=1
    )
    test_db_session.flush()
    assert [item["id"] for item in client.get(ADMIN_URL).json()] == [kept["id"]]
    assert expired["id"] not in str(client.get(ADMIN_URL).json())


def test_the_list_can_be_filtered_by_company(app_client, boss, org, org_boss, make_org):
    other = make_org(name="Test Org B")
    client = _as(app_client, "boss")
    _invite(client, org, role="viewer", email=f"uno@{TEST_EMAIL_DOMAIN}")
    _invite(client, other, email=f"dos@{TEST_EMAIL_DOMAIN}")
    assert len(client.get(ADMIN_URL).json()) == 2
    only = client.get(ADMIN_URL, params={"organization_id": other.id}).json()
    assert [item["email"] for item in only] == [f"dos@{TEST_EMAIL_DOMAIN}"]


def test_cancelling_kills_the_link(app_client, boss, org, mailer):
    client = _as(app_client, "boss")
    created = _invite(client, org).json()
    assert client.post(f"{ADMIN_URL}/{created['id']}/cancel").status_code == 204
    assert _details(client, token_from(mailer.sent[0])).status_code == 404
    assert client.get(ADMIN_URL).json() == []


def test_resending_sends_a_new_link_and_kills_the_old_one(app_client, boss, org, mailer):
    client = _as(app_client, "boss")
    created = _invite(client, org).json()
    response = client.post(f"{ADMIN_URL}/{created['id']}/resend")
    assert response.status_code == 200
    assert response.json()["id"] != created["id"] and response.json()["email"] == INVITED
    old, new = (token_from(mail) for mail in mailer.sent)
    assert old != new
    assert _details(client, old).status_code == 404 and _details(client, new).status_code == 200
    assert len(client.get(ADMIN_URL).json()) == 1


def test_cancel_and_resend_of_an_unknown_or_closed_invitation_are_404(app_client, boss, org, mailer):
    client = _as(app_client, "boss")
    ghost = "00000000-0000-0000-0000-000000000000"
    assert client.post(f"{ADMIN_URL}/{ghost}/cancel").status_code == 404
    assert client.post(f"{ADMIN_URL}/{ghost}/resend").status_code == 404
    created = _invite(client, org).json()
    _accept(app_client, token_from(mailer.sent[0]))
    _as(app_client, "boss")
    assert client.post(f"{ADMIN_URL}/{created['id']}/cancel").status_code == 404  # already accepted
    assert client.post(f"{ADMIN_URL}/{created['id']}/resend").status_code == 404


def test_a_second_mail_to_the_same_address_waits_for_the_minimum_interval(app_client, boss, org, mailer, monkeypatch):
    monkeypatch.setattr(settings, "mail_min_interval_seconds", 60)
    client = _as(app_client, "boss")
    assert _invite(client, org).status_code == 201
    assert _invite(client, org).status_code == 429
    assert len(mailer.sent) == 1


def test_the_hourly_cap_per_address_is_429(app_client, boss, org, mailer, monkeypatch):
    monkeypatch.setattr(settings, "mail_max_per_hour", 2)
    client = _as(app_client, "boss")
    assert _invite(client, org).status_code == 201
    assert _invite(client, org).status_code == 201
    assert _invite(client, org).status_code == 429
    assert len(mailer.sent) == 2


def test_the_global_hourly_cap_counts_invitations_too(app_client, boss, org, mailer, monkeypatch):
    monkeypatch.setattr(settings, "mail_max_global_per_hour", 1)
    client = _as(app_client, "boss")
    assert _invite(client, org).status_code == 201
    assert _invite(client, org, email=f"otro@{TEST_EMAIL_DOMAIN}").status_code == 429
    assert len(mailer.sent) == 1


# --- who may use the admin endpoints -------------------------------------------------------------------------


def test_a_company_admin_cannot_use_the_general_admin_endpoints(app_client, org, org_boss):
    client = _as(app_client, "orgboss")
    assert client.get(ADMIN_URL).status_code == 403
    assert _invite(client, org).status_code == 403


def test_a_viewer_cannot_invite(app_client, org, make_user):
    make_user(username="lector", organization_id=org.id)
    client = _as(app_client, "lector")
    assert client.get(ORG_URL).status_code == 403
    assert _org_invite(client).status_code == 403


# --- the company admin invites a viewer ----------------------------------------------------------------------


def test_a_company_admin_invites_a_viewer_of_its_own_company(
    app_client, org, org_boss, mailer, test_db_session, make_radar
):
    client = _as(app_client, "orgboss")
    response = _org_invite(client, radar_views=["TSTA"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["role"] == "viewer" and body["organization_id"] == org.id and body["radar_views"] == ["TSTA"]
    assert [mail.to for mail in mailer.sent] == [INVITED]
    assert _invitation(test_db_session).invited_by == org_boss.id
    # It can only hand out views its institution has (decision C4), like when it creates a user: nothing is sent.
    make_radar("TSTC")  # a radar the institution does not have
    other = f"otro@{TEST_EMAIL_DOMAIN}"
    for views in (["TSTC"], ["TSTA", "TSTC"], ["*"]):
        assert _org_invite(client, email=other, radar_views=views).status_code == 403
    assert len(mailer.sent) == 1 and _invitation(test_db_session, other) is None


def test_the_company_admin_cannot_choose_the_company_or_the_role(app_client, org, org_boss, make_org):
    other = make_org(name="Test Org B")
    response = _org_invite(_as(app_client, "orgboss"), organization_id=other.id, role="org_admin")
    assert response.status_code == 201
    assert response.json()["organization_id"] == org.id and response.json()["role"] == "viewer"


def test_the_company_admin_sees_and_cancels_only_its_own_invitations(
    app_client, boss, org, org_boss, make_org, make_user
):
    other = make_org(name="Test Org B")
    make_user(username="otherboss", role="org_admin", organization_id=other.id)
    foreign = _invite(_as(app_client, "boss"), other, role="viewer", email=f"ajena@{TEST_EMAIL_DOMAIN}").json()
    mine = _org_invite(_as(app_client, "orgboss")).json()
    client = _as(app_client, "orgboss")
    assert [item["id"] for item in client.get(ORG_URL).json()] == [mine["id"]]
    assert client.post(f"{ORG_URL}/{foreign['id']}/cancel").status_code == 404
    assert client.post(f"{ORG_URL}/{foreign['id']}/resend").status_code == 404
    assert client.post(f"{ORG_URL}/{mine['id']}/cancel").status_code == 204


def test_the_company_admin_can_resend(app_client, org, org_boss, mailer):
    client = _as(app_client, "orgboss")
    mine = _org_invite(client).json()
    assert client.post(f"{ORG_URL}/{mine['id']}/resend").status_code == 200
    assert len(mailer.sent) == 2


def test_the_company_admin_cannot_invite_over_the_seat_limit(app_client, make_org, make_user):
    small = make_org(name="Test Org B", seat_limit=1)
    make_user(username="orgboss", role="org_admin", organization_id=small.id)  # the only seat
    assert _org_invite(_as(app_client, "orgboss")).status_code == 409


def test_a_company_admin_can_invite_an_account_that_has_no_institution(app_client, org, org_boss, make_user, mailer):
    make_user(username="yaexiste", email=INVITED)
    response = _org_invite(_as(app_client, "orgboss"))
    assert response.status_code == 201 and response.json()["existing_account"] is True
    assert [mail.to for mail in mailer.sent] == [INVITED]


# --- the person opens the link --------------------------------------------------------------------------------


def test_the_link_shows_the_company_the_mail_and_the_role(app_client, boss, org, mailer, google_on):
    _invite(_as(app_client, "boss"), org)
    response = _details(app_client, token_from(mailer.sent[0]))
    assert response.status_code == 200
    assert response.json() == {
        "organization_name": org.name,
        "email": INVITED,
        "role": "org_admin",
        "google_available": True,
        "account_exists": False,
    }


def test_google_is_not_offered_when_it_is_not_configured(app_client, boss, org, mailer):
    _invite(_as(app_client, "boss"), org)
    assert _details(app_client, token_from(mailer.sent[0])).json()["google_available"] is False


def test_every_bad_link_gets_the_same_generic_404(app_client, boss, org, mailer, test_db_session):
    client = _as(app_client, "boss")
    _invite(client, org)
    live = token_from(mailer.sent[0])
    _invitation(test_db_session).expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    test_db_session.flush()
    answers = [
        _details(client, live),  # expired
        _details(client, "A" * 43),  # well formed, unknown
        _details(client, "corto"),  # malformed
        _details(client, ""),
    ]
    assert {r.status_code for r in answers} == {404}
    assert len({r.json()["detail"] for r in answers}) == 1


@pytest.mark.parametrize("token", ["' OR 1=1 --", "../../etc/passwd", "<script>alert(1)</script>", "x" * 43 + "\n"])
def test_hostile_tokens_are_a_404_never_a_500(app_client, token):
    assert _details(app_client, token).status_code == 404
    assert _accept(app_client, token).status_code == 404


@pytest.mark.parametrize("token", ["a" * 5000, "\u0000" * 43])
def test_tokens_that_cannot_even_be_stored_are_refused_up_front(app_client, token):
    # The same rule as the other public bodies (StrictText, and a size cap): a 422, never a 500.
    assert _details(app_client, token).status_code == 422
    assert _accept(app_client, token).status_code == 422


# --- accepting with the form ---------------------------------------------------------------------------------


def test_the_company_admin_accepts_and_comes_in_logged_in(app_client, boss, org, mailer, test_db_session):
    _invite(_as(app_client, "boss"), org)
    app_client.cookies.clear()
    response = _accept(app_client, token_from(mailer.sent[0]), full_name="Ana Pérez")
    assert response.status_code == 200, response.text
    assert response.json()["username"] == "nuevo" and response.json()["role"] == "org_admin"
    assert app_client.get("/api/v1/auth/me").status_code == 200  # the session cookies work
    user = _user(test_db_session, "nuevo")
    assert user.organization_id == org.id and user.role == "org_admin"
    assert user.email == INVITED and user.email_verified_at is not None and user.full_name == "Ana Pérez"
    assert _invitation(test_db_session).accepted_at is not None


def test_the_new_account_can_log_in_with_its_password(app_client, boss, org, mailer):
    _invite(_as(app_client, "boss"), org)
    _accept(app_client, token_from(mailer.sent[0]))
    app_client.cookies.clear()
    assert (
        app_client.post("/api/v1/auth/login", json={"username": "nuevo", "password": TEST_PASSWORD}).status_code == 200
    )


def test_the_link_works_once(app_client, boss, org, mailer):
    _invite(_as(app_client, "boss"), org)
    token = token_from(mailer.sent[0])
    assert _accept(app_client, token).status_code == 200
    assert _accept(app_client, token, username="otro").status_code == 404
    assert _details(app_client, token).status_code == 404


def test_an_expired_link_cannot_be_accepted(app_client, boss, org, mailer, test_db_session):
    _invite(_as(app_client, "boss"), org)
    _invitation(test_db_session).expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    test_db_session.flush()
    assert _accept(app_client, token_from(mailer.sent[0])).status_code == 404
    assert test_db_session.query(User).filter(User.username == "nuevo").count() == 0


def test_a_cancelled_link_cannot_be_accepted(app_client, boss, org, mailer):
    client = _as(app_client, "boss")
    created = _invite(client, org).json()
    client.post(f"{ADMIN_URL}/{created['id']}/cancel")
    assert _accept(client, token_from(mailer.sent[0])).status_code == 404


def test_a_viewer_starts_with_the_views_the_company_admin_chose(app_client, org, org_boss, mailer, test_db_session):
    _org_invite(_as(app_client, "orgboss"), radar_views=["TSTA"])
    app_client.cookies.clear()
    assert _accept(app_client, token_from(mailer.sent[0])).status_code == 200
    user = _user(test_db_session, "nuevo")
    assert user.role == "viewer" and user.organization_id == org.id
    assert perms.stored_radar_views(user) == ["TSTA"]


def test_without_a_list_the_viewer_starts_with_a_copy_of_the_company_views(
    app_client, org, org_boss, mailer, test_db_session
):
    _org_invite(_as(app_client, "orgboss"))
    app_client.cookies.clear()
    _accept(app_client, token_from(mailer.sent[0]))
    assert perms.stored_radar_views(_user(test_db_session, "nuevo")) == ["TSTA", "TSTB"]


def test_an_empty_list_means_no_views(app_client, org, org_boss, mailer, test_db_session):
    _org_invite(_as(app_client, "orgboss"), radar_views=[])
    app_client.cookies.clear()
    _accept(app_client, token_from(mailer.sent[0]))
    assert perms.stored_radar_views(_user(test_db_session, "nuevo")) == []


@pytest.mark.parametrize(
    "bad",
    [
        {"username": "ab"},
        {"username": "con@arroba"},
        {"username": "x" * 33},
        {"password": "corta"},
        {"password": "      "},
        {"password": "nuevo"},
    ],
)
def test_invalid_account_data_is_422_and_the_link_stays_alive(app_client, boss, org, mailer, test_db_session, bad):
    _invite(_as(app_client, "boss"), org)
    token = token_from(mailer.sent[0])
    assert _accept(app_client, token, **bad).status_code == 422
    assert _details(app_client, token).status_code == 200
    assert test_db_session.query(User).filter(User.email == INVITED).count() == 0


def test_a_taken_username_is_409_and_the_link_stays_alive(app_client, boss, org, mailer, make_user):
    make_user(username="nuevo")
    _invite(_as(app_client, "boss"), org)
    token = token_from(mailer.sent[0])
    assert _accept(app_client, token).status_code == 409
    assert _accept(app_client, token, username="otro-nombre").status_code == 200


def test_the_terms_are_required_when_the_site_asks_for_them(app_client, boss, org, mailer):
    _invite(_as(app_client, "boss"), org)
    token = token_from(mailer.sent[0])
    response = _accept(app_client, token, accept_terms=False)
    assert response.status_code == 422 and "términos" in response.json()["detail"]
    assert _details(app_client, token).status_code == 200


def test_the_terms_are_not_asked_when_they_are_off(app_client, boss, org, mailer, monkeypatch):
    monkeypatch.setattr(settings, "terms_required", False)
    _invite(_as(app_client, "boss"), org)
    assert _accept(app_client, token_from(mailer.sent[0]), accept_terms=False).status_code == 200


def test_the_reserved_seat_is_still_there_when_the_person_arrives(app_client, boss, make_org, mailer, test_db_session):
    small = make_org(name="Test Org B", seat_limit=1)
    _invite(_as(app_client, "boss"), small)
    app_client.cookies.clear()
    assert _accept(app_client, token_from(mailer.sent[0])).status_code == 200
    assert _user(test_db_session, "nuevo").organization_id == small.id


def test_if_the_company_filled_up_meanwhile_it_is_409_and_the_link_stays_alive(
    app_client, boss, make_org, make_user, mailer
):
    small = make_org(name="Test Org B", seat_limit=1)
    _invite(_as(app_client, "boss"), small)
    make_user(username="colado", organization_id=small.id)  # a seat taken behind the reservation's back
    token = token_from(mailer.sent[0])
    assert _accept(app_client, token).status_code == 409
    assert _details(app_client, token).status_code == 200


def test_a_company_deactivated_meanwhile_is_409(app_client, boss, org, mailer, test_db_session):
    _invite(_as(app_client, "boss"), org)
    org.is_active = False
    test_db_session.flush()
    assert _accept(app_client, token_from(mailer.sent[0])).status_code == 409


def test_the_mail_taken_meanwhile_is_409(app_client, boss, org, mailer, make_user):
    _invite(_as(app_client, "boss"), org)
    make_user(username="ganador", email=INVITED)
    assert _accept(app_client, token_from(mailer.sent[0])).status_code == 409


def test_a_failed_accept_leaves_nothing_behind(app_client, boss, org, mailer, make_user, test_db_session):
    make_user(username="nuevo")
    _invite(_as(app_client, "boss"), org)
    _accept(app_client, token_from(mailer.sent[0]))
    assert _invitation(test_db_session).accepted_at is None
    assert test_db_session.query(User).filter(User.email == INVITED).count() == 0


# --- accepting with Google ---------------------------------------------------------------------------------


def test_google_creates_the_account_with_the_invited_role_and_company(
    app_client, boss, org, mailer, google_verifier, google_on, test_db_session
):
    _invite(_as(app_client, "boss"), org)
    app_client.cookies.clear()
    response = _accept_google(app_client, google_verifier, token_from(mailer.sent[0]))
    assert response.status_code == 200, response.text
    assert response.json()["role"] == "org_admin"
    assert app_client.get("/api/v1/auth/me").status_code == 200
    user = _user(test_db_session, response.json()["username"])
    assert user.organization_id == org.id and user.google_sub == "g-500"
    assert user.email == INVITED and user.email_verified_at is not None and user.full_name == "Invitada Pérez"
    assert _invitation(test_db_session).accepted_at is not None


def test_a_viewer_with_google_gets_the_chosen_views(
    app_client, org, org_boss, mailer, google_verifier, google_on, test_db_session
):
    _org_invite(_as(app_client, "orgboss"), radar_views=["TSTB"])
    app_client.cookies.clear()
    response = _accept_google(app_client, google_verifier, token_from(mailer.sent[0]))
    assert response.status_code == 200
    assert perms.stored_radar_views(_user(test_db_session, response.json()["username"])) == ["TSTB"]


def test_google_with_another_mail_is_refused_and_the_link_stays_alive(
    app_client, boss, org, mailer, google_verifier, google_on, test_db_session
):
    _invite(_as(app_client, "boss"), org)
    token = token_from(mailer.sent[0])
    other = GoogleIdentity(sub="g-600", email=f"otra@{TEST_EMAIL_DOMAIN}", email_verified=True, name="Otra")
    response = _accept_google(app_client, google_verifier, token, other)
    assert response.status_code == 403
    assert test_db_session.query(User).filter(User.google_sub == "g-600").count() == 0
    assert _details(app_client, token).status_code == 200


def test_google_matching_ignores_case_in_the_mail(app_client, boss, org, mailer, google_verifier, google_on):
    _invite(_as(app_client, "boss"), org)
    shouting = GoogleIdentity(sub="g-700", email=INVITED.upper(), email_verified=True, name="Ana")
    assert _accept_google(app_client, google_verifier, token_from(mailer.sent[0]), shouting).status_code == 200


def test_google_must_have_verified_the_mail(app_client, boss, org, mailer, google_verifier, google_on):
    _invite(_as(app_client, "boss"), org)
    unverified = GoogleIdentity(sub="g-800", email=INVITED, email_verified=False, name="Ana")
    assert _accept_google(app_client, google_verifier, token_from(mailer.sent[0]), unverified).status_code == 403


def test_an_invalid_google_token_is_401(app_client, boss, org, mailer, google_verifier, google_on):
    _invite(_as(app_client, "boss"), org)
    google_verifier.fail = True
    response = app_client.post(
        f"{PUBLIC_URL}/accept-google", json={"token": token_from(mailer.sent[0]), "credential": "x"}
    )
    assert response.status_code == 401


def test_google_not_configured_is_503(app_client, boss, org, mailer, google_verifier):
    _invite(_as(app_client, "boss"), org)
    assert _accept_google(app_client, google_verifier, token_from(mailer.sent[0])).status_code == 503


def test_a_google_account_already_linked_to_another_user_is_409(
    app_client, boss, org, mailer, google_verifier, google_on, make_user
):
    make_user(username="yaexiste", email=f"ya@{TEST_EMAIL_DOMAIN}", google_sub="g-500")
    _invite(_as(app_client, "boss"), org)
    assert _accept_google(app_client, google_verifier, token_from(mailer.sent[0])).status_code == 409


def test_the_google_link_works_once_too(app_client, boss, org, mailer, google_verifier, google_on):
    _invite(_as(app_client, "boss"), org)
    token = token_from(mailer.sent[0])
    assert _accept_google(app_client, google_verifier, token).status_code == 200
    assert _accept_google(app_client, google_verifier, token).status_code == 404


# --- creating a company with an invited admin ----------------------------------------------------------------


def _create_org(client, **admin):
    body = {"name": "Test Org Nueva", "seat_limit": 3, "admin": {"mode": "invite", "email": INVITED}}
    body["admin"].update(admin)
    return client.post("/api/v1/admin/organizations", json=body)


def test_creating_a_company_can_invite_its_admin(app_client, boss, mailer, test_db_session):
    response = _create_org(_as(app_client, "boss"))
    assert response.status_code == 201, response.text
    assert response.json()["pending_invitations"] == 1
    invitation = _invitation(test_db_session)
    assert invitation.role == "org_admin" and invitation.organization_id == response.json()["id"]
    assert [mail.to for mail in mailer.sent] == [INVITED]


def test_the_invited_admin_of_a_new_company_can_accept(app_client, boss, mailer, test_db_session):
    org_id = _create_org(_as(app_client, "boss")).json()["id"]
    app_client.cookies.clear()
    assert _accept(app_client, token_from(mailer.sent[0])).status_code == 200
    assert _user(test_db_session, "nuevo").organization_id == org_id


def test_if_the_invitation_cannot_be_made_the_company_is_not_created_either(
    app_client, boss, make_user, mailer, test_db_session
):
    from radar_db.models import Organization

    make_user(username="yaexiste", email=INVITED, role="admin")  # an account that cannot join an institution
    response = _create_org(_as(app_client, "boss"))
    assert response.status_code == 409
    assert test_db_session.query(Organization).filter(Organization.name == "Test Org Nueva").count() == 0
    assert not mailer.sent


def test_a_bad_mail_when_creating_a_company_is_422(app_client, boss, mailer):
    assert _create_org(_as(app_client, "boss"), email="no-es-un-mail").status_code == 422
    assert not mailer.sent
