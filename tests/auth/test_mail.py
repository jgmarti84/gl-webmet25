# tests/auth/test_mail.py
import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api.app.config import settings
from api.app.mail import templates
from api.app.mail.service import FakeMailer, MailError, OutgoingMail, SmtpMailer, build_message, mask_email, send_safely

MAIL = OutgoingMail(to="ana@ejemplo.com.ar", subject="Hola", text="texto plano", html="<p>html</p>")


@pytest.fixture
def smtp_settings(monkeypatch):
    for name, value in dict(
        mail_host="smtp.test",
        mail_port=587,
        mail_user="usuario",
        mail_password="clave",
        mail_from="no-reply@ejemplo.com.ar",
        mail_starttls=True,
        mail_use_ssl=False,
        public_base_url="https://webmet.test",
    ).items():
        monkeypatch.setattr(settings, name, value)


def test_mask_email():
    assert mask_email("juan.perez@ejemplo.com.ar") == "j***@ejemplo.com.ar"
    assert mask_email("sin-arroba") == "***"


def test_message_has_a_plain_and_an_html_part():
    message = build_message(MAIL, "no-reply@ejemplo.com.ar")
    assert message["To"] == "ana@ejemplo.com.ar"
    assert message["From"] == "no-reply@ejemplo.com.ar"
    assert message.get_body(("plain",)).get_content().strip() == "texto plano"
    assert "<p>html</p>" in message.get_body(("html",)).get_content()


def test_line_breaks_in_headers_are_rejected():
    injected_to = OutgoingMail(to="a@ejemplo.com.ar\nBcc: x@ejemplo.com.ar", subject="s", text="t", html="h")
    injected_subject = OutgoingMail(to="a@ejemplo.com.ar", subject="s\r\nBcc: x@e.com", text="t", html="h")
    with pytest.raises(ValueError):
        build_message(injected_to, "n@e.com")
    with pytest.raises(ValueError):
        build_message(injected_subject, "n@e.com")


def test_smtp_mailer_uses_starttls_login_and_sends(smtp_settings):
    with patch("api.app.mail.service.smtplib.SMTP") as smtp_class:
        client = smtp_class.return_value.__enter__.return_value
        SmtpMailer().send(MAIL)
    smtp_class.assert_called_once_with("smtp.test", 587, timeout=10)
    client.starttls.assert_called_once()
    client.login.assert_called_once_with("usuario", "clave")
    client.send_message.assert_called_once()


def test_smtp_mailer_without_credentials_does_not_log_in(smtp_settings, monkeypatch):
    monkeypatch.setattr(settings, "mail_user", "")
    monkeypatch.setattr(settings, "mail_starttls", False)
    with patch("api.app.mail.service.smtplib.SMTP") as smtp_class:
        client = smtp_class.return_value.__enter__.return_value
        SmtpMailer().send(MAIL)
    client.login.assert_not_called()
    client.starttls.assert_not_called()
    client.send_message.assert_called_once()


def test_smtp_mailer_ssl_connection(smtp_settings, monkeypatch):
    monkeypatch.setattr(settings, "mail_use_ssl", True)
    monkeypatch.setattr(settings, "mail_port", 465)
    with patch("api.app.mail.service.smtplib.SMTP_SSL") as ssl_class:
        client = ssl_class.return_value.__enter__.return_value
        SmtpMailer().send(MAIL)
    assert ssl_class.call_args.args == ("smtp.test", 465)
    client.starttls.assert_not_called()
    client.send_message.assert_called_once()


def test_smtp_failure_becomes_a_mail_error(smtp_settings):
    with patch("api.app.mail.service.smtplib.SMTP", side_effect=OSError("down")):
        with pytest.raises(MailError):
            SmtpMailer().send(MAIL)


def test_send_safely_logs_the_failure_without_the_address(caplog):
    class Broken:
        def send(self, mail):
            raise MailError("fallo")

    with caplog.at_level(logging.ERROR):
        send_safely(Broken(), MAIL)
    assert "ana@ejemplo.com.ar" not in caplog.text
    assert "a***@ejemplo.com.ar" in caplog.text


def test_fake_mailer_keeps_what_it_was_given():
    mailer = FakeMailer()
    mailer.send(MAIL)
    assert mailer.sent == [MAIL]


def test_verification_mail_has_the_link_and_the_expiry(smtp_settings, monkeypatch):
    # A trailing slash in PUBLIC_BASE_URL must not produce "//verify".
    monkeypatch.setattr(settings, "public_base_url", "https://webmet.test/")
    user = SimpleNamespace(username="ana", email="ana@ejemplo.com.ar")
    mail = templates.verification_mail(user, "T" * 43)
    assert mail.to == "ana@ejemplo.com.ar"
    # The token goes after "#": browsers never send that part to the server, so it cannot end up in a log.
    assert "https://webmet.test/verify#token=" + "T" * 43 in mail.text
    assert "https://webmet.test/verify#token=" + "T" * 43 in mail.html
    assert "?token=" not in mail.text
    assert "24 horas" in mail.text


def test_reset_mail_points_to_the_reset_page(smtp_settings):
    user = SimpleNamespace(username="ana", email="ana@ejemplo.com.ar")
    mail = templates.reset_mail(user, "R" * 43)
    assert "https://webmet.test/reset#token=" + "R" * 43 in mail.text
    assert "60 minutos" in mail.text


def test_account_exists_mail_points_to_recovery(smtp_settings):
    user = SimpleNamespace(username="ana", email="ana@ejemplo.com.ar")
    mail = templates.account_exists_mail(user)
    assert "https://webmet.test/forgot" in mail.text
    assert "ana" in mail.text
    assert "token=" not in mail.text


def test_values_are_escaped_in_the_html(smtp_settings):
    user = SimpleNamespace(username="<script>alert(1)</script>", email="ana@ejemplo.com.ar")
    mail = templates.verification_mail(user, "T" * 43)
    assert "<script>" not in mail.html
    assert "&lt;script&gt;" in mail.html
