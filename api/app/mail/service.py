# api/app/mail/service.py
"""Outgoing e-mail. Routers depend on get_mailer(); tests replace it with FakeMailer."""

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import List, Protocol

from ..config import settings

logger = logging.getLogger(__name__)

# Seconds to wait for the SMTP server, so a stuck server cannot hold a background task forever.
SMTP_TIMEOUT_SECONDS = 10


class MailError(Exception):
    """The mail could not be delivered to the SMTP server."""


@dataclass(frozen=True)
class OutgoingMail:
    """One message ready to send: plain text and HTML versions of the same body."""

    to: str
    subject: str
    text: str
    html: str


class Mailer(Protocol):
    """Anything that can send an OutgoingMail. Lets tests swap the real SMTP sender for a fake one."""

    def send(self, mail: OutgoingMail) -> None: ...


def mask_email(address: str) -> str:
    """j***@domain.com: enough to recognize it in a log, not enough to read it."""
    local, _, domain = address.partition("@")
    return f"{local[:1]}***@{domain}" if domain else "***"


def build_message(mail: OutgoingMail, sender: str) -> EmailMessage:
    """Build the MIME message. EmailMessage refuses line breaks in headers, which closes header injection
    (e.g. a "to" value like "a@x.com\\nBcc: victim@x.com")."""
    message = EmailMessage()
    message["From"] = sender
    message["To"] = mail.to
    message["Subject"] = mail.subject
    message.set_content(mail.text)
    message.add_alternative(mail.html, subtype="html")
    return message


class SmtpMailer:
    """Sends through the SMTP server of settings (MAIL_HOST, MAIL_PORT, MAIL_USER...)."""

    def _connect(self):
        # SSL: encrypted from the first byte (port 465). Otherwise a plain connection that may be upgraded
        # with STARTTLS in send().
        if settings.mail_use_ssl:
            return smtplib.SMTP_SSL(
                settings.mail_host,
                settings.mail_port,
                timeout=SMTP_TIMEOUT_SECONDS,
                context=ssl.create_default_context(),
            )
        return smtplib.SMTP(settings.mail_host, settings.mail_port, timeout=SMTP_TIMEOUT_SECONDS)

    def send(self, mail: OutgoingMail) -> None:
        message = build_message(mail, settings.mail_from)
        try:
            with self._connect() as client:
                # STARTTLS makes starttls() raise if the server does not offer it: the send fails instead of
                # going out in clear text. Never combined with SSL (already encrypted).
                if settings.mail_starttls and not settings.mail_use_ssl:
                    client.starttls(context=ssl.create_default_context())
                # Some servers (a local test mailbox, an internal relay) need no login.
                if settings.mail_user:
                    client.login(settings.mail_user, settings.mail_password)
                client.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            # Only the class name: the text of the error can carry addresses.
            raise MailError(f"SMTP: {exc.__class__.__name__}") from exc


class FakeMailer:
    """Keeps the mails in memory (tests)."""

    def __init__(self) -> None:
        self.sent: List[OutgoingMail] = []

    def send(self, mail: OutgoingMail) -> None:
        self.sent.append(mail)


def send_safely(mailer: Mailer, mail: OutgoingMail) -> None:
    """Background-task wrapper: a failure is logged (with the address masked) and never raised.

    The request has already answered by the time this runs; the person can ask for the mail again.
    """
    try:
        mailer.send(mail)
    except MailError as exc:
        logger.error("No se pudo enviar un mail a %s (%s)", mask_email(mail.to), exc)


_mailer = SmtpMailer()


def get_mailer() -> Mailer:
    """FastAPI dependency; tests override it with a FakeMailer."""
    return _mailer
