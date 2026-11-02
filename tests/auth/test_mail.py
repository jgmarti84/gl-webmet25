# tests/auth/test_mail.py
import logging
import re
import threading
import time
from email.utils import parseaddr
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api.app.config import settings
from api.app.mail import service as mail_service
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
    assert parseaddr(message["From"])[1] == "no-reply@ejemplo.com.ar"  # the address is the configured one
    assert message.get_body(("plain",)).get_content().strip() == "texto plano"
    assert "<p>html</p>" in message.get_body(("html",)).get_content()


# --- sender, automatic-mail headers and the logo ------------------------------------------------


def test_the_sender_shows_a_no_reply_name():
    message = build_message(MAIL, "no-reply@ejemplo.com.ar")
    assert parseaddr(message["From"]) == ("WebMet25 (no responder)", "no-reply@ejemplo.com.ar")


def test_a_sender_that_already_has_a_name_keeps_it():
    message = build_message(MAIL, "Observatorio <info@ejemplo.com.ar>")
    assert parseaddr(message["From"]) == ("Observatorio", "info@ejemplo.com.ar")


def test_the_mail_is_marked_as_automatic_and_has_no_reply_to():
    message = build_message(MAIL, "no-reply@ejemplo.com.ar")
    assert message["Auto-Submitted"] == "auto-generated"
    assert message["X-Auto-Response-Suppress"] == "All"  # asks out-of-office replies not to answer
    assert message["Reply-To"] is None  # a reply goes nowhere: the text tells the person where to write


def _inline_images(message):
    """The image parts of the message that travel inside it."""
    return [part for part in message.walk() if part.get_content_maintype() == "image"]


def test_the_logo_travels_inside_the_mail_when_the_html_uses_it():
    with_logo = OutgoingMail(
        to="ana@ejemplo.com.ar", subject="s", text="t", html='<p><img src="cid:logo-ohmc" alt="x"></p>'
    )
    images = _inline_images(build_message(with_logo, "no-reply@ejemplo.com.ar"))
    assert len(images) == 1
    assert images[0].get_content_type() == "image/png"
    assert images[0]["Content-ID"] == "<logo-ohmc>"
    assert images[0].get_content_disposition() == "inline"
    assert images[0].get_payload(decode=True).startswith(b"\x89PNG")


def test_a_mail_that_does_not_use_the_logo_carries_no_image():
    assert _inline_images(build_message(MAIL, "no-reply@ejemplo.com.ar")) == []


def test_the_logo_file_is_a_real_small_png():
    assert mail_service.LOGO_PATH.is_file()
    data = mail_service.LOGO_PATH.read_bytes()
    assert data.startswith(b"\x89PNG")
    assert len(data) < 60_000  # it goes in every mail: keep it light


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


# --- design of the mails (spec: no visible token, no-reply notice, logo) ------------------------


def _visible_text(html: str) -> str:
    """What a person reads in the HTML mail: the tags (and so the address inside href) are not text."""
    return re.sub(r"<[^>]+>", " ", html)


def _all_mails(smtp_settings):
    user = SimpleNamespace(username="ana", email="ana@ejemplo.com.ar")
    return {
        "verification": templates.verification_mail(user, "T" * 43),
        "reset": templates.reset_mail(user, "R" * 43),
        "exists": templates.account_exists_mail(user),
    }


def test_the_token_is_inside_the_button_but_never_shown_as_text(smtp_settings):
    mails = _all_mails(smtp_settings)
    for name, token in (("verification", "T" * 43), ("reset", "R" * 43)):
        mail = mails[name]
        assert (
            f'href="https://webmet.test/{"verify" if name == "verification" else "reset"}#token={token}"' in mail.html
        )
        assert token not in _visible_text(mail.html), name  # nobody reads it in the body
        assert "#token" not in _visible_text(mail.html), name


def test_the_text_version_keeps_the_full_link_for_clients_without_html(smtp_settings):
    mails = _all_mails(smtp_settings)
    assert "https://webmet.test/verify#token=" + "T" * 43 in mails["verification"].text
    assert "https://webmet.test/reset#token=" + "R" * 43 in mails["reset"].text


def test_the_html_fallback_names_the_site_without_a_token(smtp_settings):
    mails = _all_mails(smtp_settings)
    # If the button does not work the person is sent to the page where a new mail can be asked for.
    assert "https://webmet.test/login" in _visible_text(mails["verification"].html)  # where "Reenviar mail" lives
    assert "https://webmet.test/forgot" in _visible_text(mails["reset"].html)
    assert "https://webmet.test/forgot" in _visible_text(mails["exists"].html)


def test_every_mail_says_not_to_reply_and_where_to_write(smtp_settings):
    for name, mail in _all_mails(smtp_settings).items():
        for body in (mail.text, _visible_text(mail.html)):
            assert "no respondas a este mail" in body.lower(), name
            assert "info@ohmc.ar" in body, name


def test_every_html_mail_shows_the_logo(smtp_settings):
    for name, mail in _all_mails(smtp_settings).items():
        assert 'src="cid:logo-ohmc"' in mail.html, name
        assert 'alt="Observatorio Hidro-Meteorológico de la Provincia de Córdoba"' in mail.html, name


def test_the_html_mail_is_a_complete_document(smtp_settings):
    for name, mail in _all_mails(smtp_settings).items():
        assert mail.html.lstrip().lower().startswith("<!doctype html>"), name
        assert '<meta charset="utf-8">' in mail.html.lower(), name


def test_a_username_cannot_break_out_of_the_new_layout(smtp_settings):
    user = SimpleNamespace(username='"><img src=x onerror=alert(1)>', email="ana@ejemplo.com.ar")
    for mail in (templates.verification_mail(user, "T" * 43), templates.reset_mail(user, "R" * 43)):
        assert "<img src=x" not in mail.html  # the logo is the only <img>, and it is ours (src="cid:...")
        assert "&lt;img src=x onerror=alert(1)&gt;" in mail.html  # the hostile name is shown as plain text


# --- own thread pool for sending ---------------------------------------------------


class _SlowMailer:
    """A mail server that hangs until the test lets it go (release), like a stuck SMTP server."""

    def __init__(self):
        self.release = threading.Event()
        self.sent = []

    def send(self, mail):
        self.release.wait(5)
        self.sent.append(mail)


def test_queueing_a_mail_does_not_wait_for_the_smtp_server():
    # The send runs in the mail threads: whoever queues it (a request of the API) is free at once, even while the
    # mail server hangs, so a slow SMTP never holds the threads that serve radars, login or /auth/check.
    slow = _SlowMailer()
    start = time.monotonic()
    assert mail_service.queue_mail(slow, MAIL) is True
    assert time.monotonic() - start < 0.5
    assert slow.sent == []  # still waiting for the server
    slow.release.set()
    for _ in range(100):  # the mail still goes out once the server answers
        if slow.sent:
            break
        time.sleep(0.05)
    assert slow.sent == [MAIL]


def test_a_full_queue_drops_the_mail_and_warns(monkeypatch, caplog):
    # With the server down for long, mails must not pile up in memory: past the limit they are dropped (the person
    # can ask again) and the log says so, with the address masked.
    monkeypatch.setattr(mail_service, "MAIL_QUEUE_LIMIT", 1)
    slow = _SlowMailer()
    try:
        with caplog.at_level(logging.WARNING, logger=mail_service.logger.name):
            assert mail_service.queue_mail(slow, MAIL) is True
            assert mail_service.queue_mail(slow, MAIL) is False
        assert "a***@ejemplo.com.ar" in caplog.text and "ana@ejemplo.com.ar" not in caplog.text
    finally:
        slow.release.set()
