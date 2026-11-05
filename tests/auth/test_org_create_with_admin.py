# tests/auth/test_org_create_with_admin.py
"""Creating a company with its admin and its radar views in ONE request (spec C, follow-up).

POST /api/v1/admin/organizations takes, besides name, seat_limit and is_active:
  - "admin": {"mode": "new", username, password, full_name?, email?}  a brand new company admin, or
             {"mode": "existing", "user_id": N}                        an existing viewer WITHOUT a company;
  - "radar_detail_view": [...]  the company's views (radar codes, or ["*"]).
Everything happens in one transaction: if any part fails, nothing is created, not even the company.
"""

import pytest

from radar_db.models import Organization, Permission, User

from .conftest import TEST_PASSWORD, login

URL = "/api/v1/admin/organizations"
NAME = "Test Org Nueva"


def _as_admin(app_client, make_user):
    make_user(username="boss", role="admin")
    login(app_client, "boss")


def _body(**extra):
    return {"name": NAME, "seat_limit": 3, **extra}


def _new_admin(**overrides):
    admin = {"mode": "new", "username": "jefa", "password": TEST_PASSWORD, "full_name": "Jefa Nueva"}
    admin.update(overrides)
    return admin


def _company(db, name=NAME):
    return db.query(Organization).filter_by(name=name).one_or_none()


def _own(db, user, *resources):
    """Store a user's own detail-view permissions, bypassing the service."""
    for resource in resources:
        db.add(Permission(user_id=user.id, action="radar.detail_view", resource=resource))
    db.flush()
    db.refresh(user)


# --- without the new fields nothing changes -------------------------------------------------------------------


def test_a_company_without_admin_or_views_is_created_as_before(app_client, make_user, test_db_session):
    _as_admin(app_client, make_user)
    response = app_client.post(URL, json=_body())
    assert response.status_code == 201
    body = response.json()
    assert body["seats_used"] == 0 and body["radar_detail_views"] == []


# --- a new admin ---------------------------------------------------------------------------------------------


def test_a_new_admin_is_created_with_the_company(app_client, make_user, test_db_session):
    _as_admin(app_client, make_user)
    response = app_client.post(URL, json=_body(admin=_new_admin()))
    assert response.status_code == 201
    body = response.json()
    assert body["seats_used"] == 1  # the admin takes a seat
    admin = test_db_session.query(User).filter_by(username="jefa").one()
    assert admin.role == "org_admin" and admin.organization_id == body["id"] and admin.full_name == "Jefa Nueva"
    assert admin.is_active is True


def test_the_new_admin_can_log_in_as_company_admin(app_client, make_user):
    _as_admin(app_client, make_user)
    app_client.post(URL, json=_body(admin=_new_admin()))
    response = app_client.post("/api/v1/auth/login", json={"username": "jefa", "password": TEST_PASSWORD})
    assert response.status_code == 200 and response.json()["role"] == "org_admin"


def test_the_new_admin_takes_the_mail_and_normalizes_the_username(app_client, make_user, test_db_session):
    _as_admin(app_client, make_user)
    admin = _new_admin(username="  JefaMail ", email="Jefa@Example.com")
    assert app_client.post(URL, json=_body(admin=admin)).status_code == 201
    created = test_db_session.query(User).filter_by(username="jefamail").one()
    assert created.email == "jefa@example.com"


def test_a_taken_username_is_a_409_and_the_company_is_not_created(app_client, make_user, test_db_session):
    _as_admin(app_client, make_user)
    make_user(username="jefa")
    response = app_client.post(URL, json=_body(admin=_new_admin()))
    assert response.status_code == 409
    assert _company(test_db_session) is None


def test_a_taken_mail_is_a_409_and_the_company_is_not_created(app_client, make_user, test_db_session):
    _as_admin(app_client, make_user)
    make_user(username="otro", email="jefa@example.com")
    response = app_client.post(URL, json=_body(admin=_new_admin(email="jefa@example.com")))
    assert response.status_code == 409
    assert _company(test_db_session) is None


def test_a_weak_password_is_a_422_and_the_company_is_not_created(app_client, make_user, test_db_session):
    _as_admin(app_client, make_user)
    response = app_client.post(URL, json=_body(admin=_new_admin(password="corta")))
    assert response.status_code == 422
    assert _company(test_db_session) is None
    assert test_db_session.query(User).filter_by(username="jefa").count() == 0


# --- an existing admin ---------------------------------------------------------------------------------------


def test_an_existing_viewer_without_company_becomes_the_company_admin(app_client, make_user, test_db_session):
    _as_admin(app_client, make_user)
    viewer = make_user(username="juan")
    before = viewer.token_version
    response = app_client.post(URL, json=_body(admin={"mode": "existing", "user_id": viewer.id}))
    assert response.status_code == 201
    body = response.json()
    assert body["seats_used"] == 1
    test_db_session.refresh(viewer)
    assert viewer.role == "org_admin" and viewer.organization_id == body["id"]
    assert viewer.token_version > before  # its sessions were closed: what it can do changed


def test_an_existing_admin_gets_the_company_views_in_place_of_its_own(
    app_client, make_user, make_radar, test_db_session
):
    from api.app.auth import permissions as perms

    make_radar("TSTA")
    make_radar("TSTB")
    _as_admin(app_client, make_user)
    viewer = make_user(username="juan")
    _own(test_db_session, viewer, "TSTB")
    response = app_client.post(
        URL, json=_body(admin={"mode": "existing", "user_id": viewer.id}, radar_detail_view=["TSTA"])
    )
    assert response.status_code == 201
    test_db_session.refresh(viewer)
    assert perms.stored_radar_views(viewer) == ["TSTA"]  # replaced by the company's list, not merged


def test_an_unknown_user_is_a_404_and_the_company_is_not_created(app_client, make_user, test_db_session):
    _as_admin(app_client, make_user)
    response = app_client.post(URL, json=_body(admin={"mode": "existing", "user_id": 999999999}))
    assert response.status_code == 404
    assert _company(test_db_session) is None


def test_a_viewer_of_another_company_cannot_be_chosen(app_client, make_user, make_org, test_db_session):
    _as_admin(app_client, make_user)
    other = make_org(name="Test Org Otra")
    member = make_user(username="juan", organization_id=other.id)
    response = app_client.post(URL, json=_body(admin={"mode": "existing", "user_id": member.id}))
    assert response.status_code == 422
    assert _company(test_db_session) is None
    test_db_session.refresh(member)
    assert member.organization_id == other.id and member.role == "viewer"  # not moved


def test_a_company_admin_cannot_be_chosen(app_client, make_user, make_org, test_db_session):
    from api.app.auth import organizations as orgs

    _as_admin(app_client, make_user)
    other = make_org(name="Test Org Otra")
    boss = test_db_session.query(User).filter_by(username="boss").one()
    chief = orgs.create_member(
        test_db_session,
        other.id,
        {"username": "jefe", "password": TEST_PASSWORD, "full_name": None, "email": None},
        "org_admin",
        boss,
    )
    response = app_client.post(URL, json=_body(admin={"mode": "existing", "user_id": chief.id}))
    assert response.status_code == 422
    assert _company(test_db_session) is None


def test_the_general_admin_cannot_be_chosen(app_client, make_user, test_db_session):
    _as_admin(app_client, make_user)
    other_admin = make_user(username="boss2", role="admin")
    response = app_client.post(URL, json=_body(admin={"mode": "existing", "user_id": other_admin.id}))
    assert response.status_code == 422
    assert _company(test_db_session) is None
    test_db_session.refresh(other_admin)
    assert other_admin.organization_id is None and other_admin.role == "admin"


def test_an_inactive_viewer_cannot_be_chosen(app_client, make_user, test_db_session):
    _as_admin(app_client, make_user)
    sleeper = make_user(username="dormido", is_active=False)
    response = app_client.post(URL, json=_body(admin={"mode": "existing", "user_id": sleeper.id}))
    assert response.status_code == 422
    assert _company(test_db_session) is None


# --- the radar views of the company --------------------------------------------------------------------------


def test_the_company_is_created_with_its_views(app_client, make_user, make_radar):
    make_radar("TSTA")
    make_radar("TSTB")
    _as_admin(app_client, make_user)
    response = app_client.post(URL, json=_body(radar_detail_view=["TSTA", "TSTB"]))
    assert response.status_code == 201
    assert response.json()["radar_detail_views"] == ["TSTA", "TSTB"]


def test_the_wildcard_gives_every_radar(app_client, make_user):
    _as_admin(app_client, make_user)
    response = app_client.post(URL, json=_body(radar_detail_view=["*"]))
    assert response.status_code == 201 and response.json()["radar_detail_views"] == ["*"]


def test_an_unknown_radar_is_a_422_and_the_company_is_not_created(app_client, make_user, test_db_session):
    _as_admin(app_client, make_user)
    response = app_client.post(URL, json=_body(radar_detail_view=["NOPE1"]))
    assert response.status_code == 422
    assert _company(test_db_session) is None


def test_a_new_admin_starts_with_the_company_views(app_client, make_user, make_radar, test_db_session):
    from api.app.auth import permissions as perms

    make_radar("TSTA")
    _as_admin(app_client, make_user)
    response = app_client.post(URL, json=_body(admin=_new_admin(), radar_detail_view=["TSTA"]))
    assert response.status_code == 201
    admin = test_db_session.query(User).filter_by(username="jefa").one()
    assert perms.stored_radar_views(admin) == ["TSTA"]  # the views are set BEFORE the admin is created
    assert perms.effective_radar_views(test_db_session, admin) == ["TSTA"]


def test_views_and_admin_together_in_one_request(app_client, make_user, make_radar, test_db_session):
    make_radar("TSTA")
    _as_admin(app_client, make_user)
    viewer = make_user(username="juan")
    body = _body(admin={"mode": "existing", "user_id": viewer.id}, radar_detail_view=["TSTA"], seat_limit=1)
    response = app_client.post(URL, json=body)
    assert response.status_code == 201
    assert response.json()["seats_used"] == 1 and response.json()["radar_detail_views"] == ["TSTA"]


# --- the rest of the rules still hold --------------------------------------------------------------------------


def test_a_taken_company_name_is_still_a_409_and_creates_no_user(app_client, make_user, make_org, test_db_session):
    _as_admin(app_client, make_user)
    make_org(name=NAME)
    response = app_client.post(URL, json=_body(admin=_new_admin()))
    assert response.status_code == 409
    assert test_db_session.query(User).filter_by(username="jefa").count() == 0


@pytest.mark.parametrize(
    "admin",
    [
        {"mode": "otra"},
        {"mode": "new"},  # no username or password
        {"mode": "existing"},  # no user_id
        {"mode": "existing", "user_id": "abc"},
        {"username": "jefa", "password": TEST_PASSWORD},  # no mode
    ],
)
def test_a_malformed_admin_block_is_a_422_and_creates_nothing(app_client, make_user, test_db_session, admin):
    _as_admin(app_client, make_user)
    assert app_client.post(URL, json=_body(admin=admin)).status_code == 422
    assert _company(test_db_session) is None


def test_only_the_general_admin_can_do_it(app_client, make_user):
    make_user(username="ana")
    login(app_client, "ana")
    assert app_client.post(URL, json=_body(admin=_new_admin())).status_code == 403
