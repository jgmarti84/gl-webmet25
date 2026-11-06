# tests/auth/test_mail_templates.py
"""Editable texts of the mails (spec F): the general admin changes the TEXT of the 4 mails, never the design.

Everything goes through the real application (`app_client`); the mails are triggered by the same endpoints the people
use (sign-up, "forgot my password", invitations) and read from the fake mailer. What is checked here:

* only the general admin can read or change the texts (401 without a session, 403 for the others);
* a mail with no saved text goes out exactly as before, and with a saved text it uses it (and `restore` brings the
  original back);
* the markers like {usuario} are replaced, a marker that the mail does not have is refused (a typo must never reach
  a real mail) and anything else with braces stays literal;
* the text cannot break the mail: no line breaks in the subject, HTML comes out escaped, SQL is only text;
* the preview shows the mail with example data and sends and saves nothing.
"""

import logging

import pytest
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from api.app.config import settings
from radar_db.models import MailTemplate

from .conftest import TEST_EMAIL_DOMAIN, login, register_payload

URL = "/api/v1/admin/mail-templates"
DOMAIN = TEST_EMAIL_DOMAIN
KEYS = ["verify_email", "reset_password", "account_exists", "invitation"]

# A valid set of texts for each mail, using only the markers that mail accepts.
TEXTS = {
    "verify_email": dict(
        subject="Hola {usuario}, falta un paso",
        heading="Confirmá tu mail",
        body="Gracias {usuario}.\n\nEl link vence en {horas} horas.",
        button="Confirmar ahora",
        footer="Si no fuiste vos, ignorá esto.",
        fallback="Si el botón falla, andá a",
    ),
    "reset_password": dict(
        subject="Cambiá tu clave, {usuario}",
        heading="Nueva clave",
        body="Pediste cambiar la clave.\n\nVence en {minutos} minutos.",
        button="Elegir clave",
        footer="Si no fuiste vos, no hagas nada.",
        fallback="Si el botón falla, andá a",
    ),
    "account_exists": dict(
        subject="Ya estás registrado",
        heading="Ya tenés cuenta",
        body="Tu usuario es {usuario}.",
        button="Recuperar clave",
        footer="Si no fuiste vos, ignorá esto.",
        fallback="Si el botón falla, andá a",
    ),
    "invitation": dict(
        subject="Invitación a {institucion}",
        heading="Sumate a {institucion}",
        body="{invitador} a {institucion} como {rol}.\n\nEl link vence el {vence}.",
        button="Aceptar ya",
        footer="Si no esperabas esto, ignorá el mensaje.",
        fallback="Si el botón falla, pedí otra invitación en",
    ),
}
FIELDS = ["subject", "heading", "body", "button", "footer", "fallback"]


@pytest.fixture(autouse=True)
def _mail_on(registration_on, monkeypatch):
    """Mail configured and no waiting between mails to one address (the caps have their own tests)."""
    monkeypatch.setattr(settings, "mail_min_interval_seconds", 0)
    monkeypatch.setattr(settings, "terms_required", False)


@pytest.fixture
def boss(make_user):
    return make_user(username="boss", role="admin")


@pytest.fixture
def admin_client(app_client, boss):
    login(app_client, "boss")
    return app_client


def _put(client, key, **overrides):
    return client.put(f"{URL}/{key}", json={**TEXTS[key], **overrides})


def _rows(db):
    return db.query(MailTemplate).count()


def _register(client, **overrides):
    return client.post("/api/v1/auth/register", json=register_payload(**overrides))


def _trigger(client, key, make_user=None, make_org=None, org_name="Test Org A"):
    """Make the app send the mail of `key`; returns the OutgoingMail that reached the fake mailer."""
    if key == "verify_email":
        assert _register(client, username="nuevo").status_code == 202
    elif key == "reset_password":
        make_user(username="ana", email=f"ana@{DOMAIN}")
        assert client.post("/api/v1/auth/forgot-password", json={"email": f"ana@{DOMAIN}"}).status_code == 202
    elif key == "account_exists":
        make_user(username="ana", email=f"ana@{DOMAIN}")
        assert _register(client, username="otra", email=f"ana@{DOMAIN}").status_code == 202
    else:
        org = make_org(name=org_name)
        body = {"email": f"invitado@{DOMAIN}", "organization_id": org.id, "role": "org_admin"}
        login(client, "boss")
        assert client.post("/api/v1/admin/invitations", json=body).status_code == 201
    return None


def _sent(mailer):
    assert mailer.sent, "no mail was sent"
    return mailer.sent[-1]


# --- who may use it -------------------------------------------------------------------------------------------

ENDPOINTS = [
    ("get", URL, None),
    ("put", f"{URL}/verify_email", TEXTS["verify_email"]),
    ("delete", f"{URL}/verify_email", None),
    ("post", f"{URL}/verify_email/preview", TEXTS["verify_email"]),
]


@pytest.mark.parametrize("method,path,body", ENDPOINTS)
def test_without_a_session_it_is_401(app_client, method, path, body):
    assert app_client.request(method, path, json=body).status_code == 401


@pytest.mark.parametrize("who", ["org_admin", "viewer"])
@pytest.mark.parametrize("method,path,body", ENDPOINTS)
def test_only_the_general_admin_gets_in(app_client, make_user, make_org, test_db_session, who, method, path, body):
    org = make_org()
    make_user(username="otro", role=who, organization_id=org.id)
    login(app_client, "otro")
    assert app_client.request(method, path, json=body).status_code == 403
    assert _rows(test_db_session) == 0


def test_a_foreign_origin_is_refused(admin_client, test_db_session):
    response = admin_client.put(
        f"{URL}/verify_email", json=TEXTS["verify_email"], headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 403
    assert _rows(test_db_session) == 0


def test_the_database_refuses_an_unknown_key(test_db_session):
    row = MailTemplate(key="otro", subject="a", heading="b", body="c", button="d", footer="e", fallback="f")
    with pytest.raises(IntegrityError):
        with test_db_session.begin_nested():
            test_db_session.add(row)
            test_db_session.flush()


# --- listing, saving, restoring -------------------------------------------------------------------------------


def test_the_list_has_the_four_mails_with_their_original_texts(admin_client, test_db_session):
    response = admin_client.get(URL)
    assert response.status_code == 200
    items = {item["key"]: item for item in response.json()}
    assert sorted(items) == sorted(KEYS)
    for item in items.values():
        assert item["customized"] is False and item["texts"] == item["defaults"]
        assert set(item["texts"]) == set(FIELDS)
        assert item["title"] and item["updated_at"] is None and item["updated_by_username"] is None
    assert [p["name"] for p in items["verify_email"]["placeholders"]] == ["usuario", "horas"]
    assert [p["name"] for p in items["invitation"]["placeholders"]] == ["institucion", "invitador", "rol", "vence"]
    assert all(p["example"] for item in items.values() for p in item["placeholders"])
    assert _rows(test_db_session) == 0


@pytest.mark.parametrize("key", KEYS)
def test_saving_keeps_the_texts_and_says_who_and_when(admin_client, test_db_session, key):
    response = _put(admin_client, key)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["key"] == key and body["customized"] is True
    assert body["texts"] == TEXTS[key] and body["defaults"] != TEXTS[key]
    assert body["updated_by_username"] == "boss" and body["updated_at"]
    assert _rows(test_db_session) == 1
    listed = {item["key"]: item for item in admin_client.get(URL).json()}
    assert listed[key]["customized"] is True and listed[key]["texts"] == TEXTS[key]
    assert all(listed[other]["customized"] is False for other in KEYS if other != key)


def test_saving_again_replaces_the_row(admin_client, test_db_session):
    _put(admin_client, "verify_email")
    assert _put(admin_client, "verify_email", subject="Otro asunto").status_code == 200
    assert _rows(test_db_session) == 1
    saved = next(item for item in admin_client.get(URL).json() if item["key"] == "verify_email")
    assert saved["texts"]["subject"] == "Otro asunto"


def test_the_texts_are_trimmed(admin_client):
    response = _put(admin_client, "verify_email", subject="  Hola {usuario}  ", button="  Ir  ")
    assert response.json()["texts"]["subject"] == "Hola {usuario}" and response.json()["texts"]["button"] == "Ir"


def test_restoring_brings_the_original_back_and_can_be_repeated(admin_client, test_db_session):
    _put(admin_client, "verify_email")
    assert admin_client.delete(f"{URL}/verify_email").status_code == 204
    assert _rows(test_db_session) == 0
    assert admin_client.delete(f"{URL}/verify_email").status_code == 204  # nothing to restore: still fine
    item = next(i for i in admin_client.get(URL).json() if i["key"] == "verify_email")
    assert item["customized"] is False and item["texts"] == item["defaults"]


@pytest.mark.parametrize("method", ["put", "delete", "post"])
def test_a_key_that_is_not_one_of_the_four_is_422(admin_client, method):
    path = f"{URL}/nope" + ("/preview" if method == "post" else "")
    body = TEXTS["verify_email"] if method != "delete" else None
    assert admin_client.request(method, path, json=body).status_code == 422


# --- the mails use the saved text -----------------------------------------------------------------------------


def test_a_mail_with_no_saved_text_goes_out_as_before(admin_client, mailer):
    _register(admin_client, username="nuevo")
    mail = _sent(mailer)
    assert mail.subject == "Verificá tu mail - WebMet25"
    assert "Verificar mi mail" in mail.text and "Si no creaste una cuenta" in mail.text


def test_verify_mail_uses_the_saved_text_and_keeps_the_fixed_parts(admin_client, mailer):
    _put(admin_client, "verify_email")
    _register(admin_client, username="nuevo")
    mail = _sent(mailer)
    assert mail.subject == "Hola nuevo, falta un paso"
    assert f"El link vence en {settings.email_verify_ttl_hours} horas." in mail.text
    assert "Confirmar ahora: https://webmet.test/verify#token=" in mail.text  # the button and its link stay in the code
    assert "Confirmá tu mail" in mail.html and "Confirmar ahora" in mail.html
    assert "cid:" in mail.html and "no respondas a este mail" in mail.html.lower()  # logo and no-reply notice stay


def test_reset_mail_uses_the_saved_text(admin_client, make_user, mailer):
    _put(admin_client, "reset_password")
    _trigger(admin_client, "reset_password", make_user=make_user)
    mail = _sent(mailer)
    assert mail.subject == "Cambiá tu clave, ana"
    assert f"Vence en {settings.password_reset_ttl_minutes} minutos." in mail.text
    assert "Elegir clave: https://webmet.test/reset#token=" in mail.text


def test_account_exists_mail_uses_the_saved_text(admin_client, make_user, mailer):
    _put(admin_client, "account_exists")
    _trigger(admin_client, "account_exists", make_user=make_user)
    mail = _sent(mailer)
    assert mail.subject == "Ya estás registrado" and "Tu usuario es ana." in mail.text
    assert "Recuperar clave: https://webmet.test/forgot" in mail.text


def test_invitation_mail_uses_the_saved_text(admin_client, make_org, mailer):
    _put(admin_client, "invitation")
    _trigger(admin_client, "invitation", make_org=make_org)
    mail = _sent(mailer)
    assert mail.subject == "Invitación a Test Org A"
    assert "boss te invitó a Test Org A como administrador de la institución" in mail.text
    assert "Aceptar ya: https://webmet.test/invitacion#token=" in mail.text


def test_the_invitation_role_marker_depends_on_the_role(admin_client, make_org, make_user, mailer):
    _put(admin_client, "invitation")
    org = make_org()
    make_user(username="jefe", role="org_admin", organization_id=org.id)
    for role, expected in (("org_admin", "administrador de la institución"), ("viewer", "usuario de la institución")):
        body = {"email": f"{role}@{DOMAIN}", "organization_id": org.id, "role": role}
        assert admin_client.post("/api/v1/admin/invitations", json=body).status_code == 201
        assert f"como {expected}" in _sent(mailer).text


def test_restoring_puts_the_original_text_back_in_the_mails(admin_client, mailer):
    _put(admin_client, "verify_email")
    admin_client.delete(f"{URL}/verify_email")
    _register(admin_client, username="nuevo")
    assert _sent(mailer).subject == "Verificá tu mail - WebMet25"


def test_if_reading_the_saved_text_fails_the_mail_still_goes_out(admin_client, mailer, monkeypatch, caplog):
    from api.app.mail import texts

    _put(admin_client, "verify_email")

    def boom(db, key):
        raise SQLAlchemyError("the table is not there")

    monkeypatch.setattr(texts, "stored_texts", boom)
    with caplog.at_level(logging.ERROR):
        assert _register(admin_client, username="nuevo").status_code == 202
    assert _sent(mailer).subject == "Verificá tu mail - WebMet25"  # the default text, not an error
    assert caplog.records  # and the failure was logged


# --- markers ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"body": "Hola {otra_cosa}."},  # a marker nobody knows
        {"subject": "Hola {institucion}"},  # a marker of another mail (the invitation's)
        {"heading": "Hola {__class__}"},  # looks like a marker, is not an allowed one
    ],
)
def test_a_marker_the_mail_does_not_have_is_422_and_nothing_is_saved(admin_client, test_db_session, overrides):
    response = _put(admin_client, "verify_email", **overrides)
    assert response.status_code == 422
    assert "{" in response.json()["detail"]  # says which marker
    assert _rows(test_db_session) == 0


def test_braces_that_are_not_a_marker_stay_as_text(admin_client, mailer):
    body = "Llaves {} y {{7*7}} y {0} y {1+1} y ${1} y %(x)s."
    assert _put(admin_client, "verify_email", body=body).status_code == 200
    _register(admin_client, username="nuevo")
    mail = _sent(mailer)
    for literal in ("{}", "{{7*7}}", "{0}", "{1+1}", "${1}", "%(x)s"):
        assert literal in mail.text


# --- the text cannot break the mail ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"subject": "Hola\nBcc: otro@ejemplo.com"},
        {"subject": "Hola\rBcc: otro@ejemplo.com"},
        {"heading": "Título\nroto"},
        {"button": "Bo\ttón"},
        {"footer": "Pie\x07"},
        {"subject": "x" * 151},
        {"heading": "x" * 121},
        {"button": "x" * 41},
        {"footer": "x" * 401},
        {"fallback": "x" * 201},
        {"body": "x" * 2001},
        {"body": "\n\n".join(["párrafo"] * 9)},
        {"subject": ""},
        {"subject": "   "},
        {"body": ""},
        {"subject": "con nulo \x00"},
    ],
)
def test_texts_that_could_break_a_mail_are_422_never_500(admin_client, test_db_session, overrides):
    assert _put(admin_client, "verify_email", **overrides).status_code == 422
    assert _rows(test_db_session) == 0


def test_a_missing_or_extra_field_is_422(admin_client, test_db_session):
    body = dict(TEXTS["verify_email"])
    missing = {k: v for k, v in body.items() if k != "footer"}
    assert admin_client.put(f"{URL}/verify_email", json=missing).status_code == 422
    assert admin_client.put(f"{URL}/verify_email", json={**body, "key": "invitation"}).status_code == 422
    assert admin_client.put(f"{URL}/verify_email", json={**body, "updated_by": 1}).status_code == 422
    assert _rows(test_db_session) == 0


def test_html_in_the_text_comes_out_escaped(admin_client, mailer):
    _put(admin_client, "verify_email", heading="<script>alert(1)</script>", body='<img src=x onerror="alert(1)">')
    _register(admin_client, username="nuevo")
    html = _sent(mailer).html
    assert "<script>alert(1)</script>" not in html and "<img src=x" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_sql_in_the_text_is_only_text(admin_client, test_db_session):
    attack = "'; DROP TABLE mail_templates; --"
    assert _put(admin_client, "verify_email", footer=attack).status_code == 200
    assert next(i for i in admin_client.get(URL).json() if i["key"] == "verify_email")["texts"]["footer"] == attack
    assert _rows(test_db_session) == 1  # the table is still there


def test_a_line_break_in_a_value_does_not_break_the_subject(admin_client, make_org, mailer):
    _put(admin_client, "invitation")
    _trigger(admin_client, "invitation", make_org=make_org, org_name="Mala\r\nBcc: otro@ejemplo.com")
    subject = _sent(mailer).subject
    assert "\n" not in subject and "\r" not in subject
    assert subject.startswith("Invitación a Mala")


# --- the preview ------------------------------------------------------------------------------------------------


def test_the_preview_shows_the_draft_with_example_data_and_sends_and_saves_nothing(
    admin_client, mailer, test_db_session
):
    draft = {**TEXTS["verify_email"], "subject": "Vista de {usuario}", "heading": "Título de prueba"}
    response = admin_client.post(f"{URL}/verify_email/preview", json=draft)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["subject"] == "Vista de ana.perez"
    assert "Título de prueba" in body["html"] and "Confirmar ahora" in body["html"]
    assert "cid:" not in body["html"]  # the logo is a public image path here, so the screen can show it
    assert not mailer.sent and _rows(test_db_session) == 0


def test_the_preview_escapes_html_and_refuses_bad_drafts(admin_client):
    shouting = {**TEXTS["verify_email"], "heading": "<script>alert(1)</script>"}
    html = admin_client.post(f"{URL}/verify_email/preview", json=shouting).json()["html"]
    assert "<script>alert(1)</script>" not in html
    assert admin_client.post(f"{URL}/verify_email/preview", json={**shouting, "heading": "{nada}"}).status_code == 422
    assert admin_client.post(f"{URL}/verify_email/preview", json={**shouting, "subject": "a\nb"}).status_code == 422


@pytest.mark.parametrize("key", KEYS)
def test_the_preview_of_every_mail_works(admin_client, key):
    response = admin_client.post(f"{URL}/{key}/preview", json=TEXTS[key])
    assert response.status_code == 200 and response.json()["subject"] and response.json()["html"]
