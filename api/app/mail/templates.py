# api/app/mail/templates.py
"""Bodies of the account mails (Spanish): plain text and HTML, values escaped."""

from datetime import datetime, timezone
from html import escape
from typing import List, Optional

from sqlalchemy.orm import Session

from radar_db.models import User

from ..config import settings
from . import texts
from .service import LOGO_CID, OutgoingMail


def link(path: str, token: Optional[str] = None) -> str:
    """Absolute link to a page of the site. rstrip avoids "//verify" when PUBLIC_BASE_URL ends with a slash.

    The token goes after "#" (the fragment), not after "?": browsers never send the fragment to the server, so the
    token cannot end up in the nginx access log (nor in any proxy log), and it is not sent as Referer either. The
    page reads it with JavaScript from location.hash.
    """
    base = settings.public_base_url.rstrip("/")
    return f"{base}{path}" + (f"#token={token}" if token else "")


# Where a person writes for help (the same address the login page shows at the bottom).
SUPPORT_ADDRESS = "info@ohmc.ar"

# Closing notice of every mail. The mails are sent from an address nobody reads.
NO_REPLY_NOTICE = (
    "Este es un mensaje automático: por favor no respondas a este mail. "
    f"Si necesitás ayuda, escribinos a {SUPPORT_ADDRESS}."
)

LOGO_ALT = "Observatorio Hidro-Meteorológico de la Provincia de Córdoba"


def _build(
    to: str,
    subject: str,
    heading: str,
    lines: List[str],
    action: str,
    url: str,
    footer: str,
    fallback_path: str,
    fallback_text: str,
) -> OutgoingMail:
    """Same layout for every mail: logo, heading, paragraphs, one button, a fallback and a footer.

    The button carries the link (and the token in it), but the HTML never WRITES the link: below the button it only
    names the site page where a new mail can be asked for (`fallback_path`, with no token), so the token is never
    visible in the body. The plain-text version, which has no button, does keep the full link.

    Every value goes through escape() in the HTML version, so a username like "<script>" cannot inject markup.
    """
    fallback_url = link(fallback_path)
    text = "\n\n".join([heading, *lines, f"{action}: {url}", footer, NO_REPLY_NOTICE])
    paragraphs = "".join(f'<p style="margin:0 0 14px">{escape(line)}</p>' for line in lines)
    html = (
        "<!DOCTYPE html>"
        '<html lang="es-AR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{escape(subject)}</title></head>"
        '<body style="margin:0;padding:0;background:#eef2f7">'
        # Outer table: the grey background, the card centered in it. Tables: mail programs ignore most CSS layout.
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="background:#eef2f7;padding:24px 12px"><tr><td align="center">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:520px;background:#ffffff;border:1px solid #dbe3ee;border-radius:8px">'
        # Logo (inline image, see service.LOGO_CID).
        '<tr><td style="padding:28px 32px 4px">'
        f'<img src="cid:{LOGO_CID}" alt="{escape(LOGO_ALT, quote=True)}" width="180" '
        'style="display:block;border:0;width:180px;height:auto"></td></tr>'
        # Body: heading, paragraphs, the button and the fallback.
        '<tr><td style="padding:12px 32px 8px;font-family:Segoe UI,Arial,sans-serif;font-size:15px;'
        'line-height:1.55;color:#1e293b">'
        f'<h2 style="margin:0 0 14px;font-size:22px;line-height:1.25;color:#0b1b3d">{escape(heading)}</h2>'
        f"{paragraphs}"
        f'<p style="margin:22px 0"><a href="{escape(url, quote=True)}" style="display:inline-block;'
        "padding:12px 22px;background:#12306b;color:#ffffff;border-radius:6px;text-decoration:none;"
        f'font-weight:600">{escape(action)}</a></p>'
        f'<p style="margin:0;font-size:13px;color:#5b6b82">{escape(fallback_text)} {escape(fallback_url)}</p>'
        "</td></tr>"
        # Footer: the specific notice of the mail, then the no-reply notice.
        '<tr><td style="padding:20px 32px 28px;font-family:Segoe UI,Arial,sans-serif;font-size:12.5px;'
        'line-height:1.5;color:#5b6b82">'
        f'<p style="margin:0 0 10px">{escape(footer)}</p>'
        '<p style="margin:0;padding-top:12px;border-top:1px solid #e3e9f1">'
        f"{escape(NO_REPLY_NOTICE)}</p>"
        "</td></tr></table></td></tr></table></body></html>"
    )
    return OutgoingMail(to=to, subject=subject, text=text, html=html)


# Where each mail's button and its fallback point: (path of the button, path named in the fallback sentence).
# The button's link is fixed here, never taken from the editable text.
_PAGES = {
    "verify_email": ("/verify", "/login"),  # a new mail is asked for from the login page
    "reset_password": ("/reset", "/forgot"),
    "account_exists": ("/forgot", "/forgot"),
    "invitation": ("/invitacion", "/login"),
}


def _mail(db: Session, key: str, to: str, values: dict, token: Optional[str] = None) -> OutgoingMail:
    """Build the mail `key`: the saved (or default) text with its markers replaced, inside the fixed layout.

    The texts come from `texts.get_texts` (the general admin may have customized them, spec F); the layout, the button
    and its link are the ones of `_build`, so editing a text can never change them.
    """
    t = texts.render_texts(texts.get_texts(db, key), values)
    button_path, fallback_path = _PAGES[key]
    return _build(
        to,
        t["subject"],
        t["heading"],
        t["paragraphs"],
        t["button"],
        link(button_path, token),
        t["footer"],
        fallback_path,
        t["fallback"],
    )


def verification_mail(db: Session, user: User, token: str) -> OutgoingMail:
    """Sent after signing up: the link proves the person controls the address."""
    values = {"usuario": user.username, "horas": settings.email_verify_ttl_hours}
    return _mail(db, "verify_email", user.email, values, token)


def reset_mail(db: Session, user: User, token: str) -> OutgoingMail:
    """Sent by "forgot my password": the link opens the page to choose a new one."""
    values = {"usuario": user.username, "minutos": settings.password_reset_ttl_minutes}
    return _mail(db, "reset_password", user.email, values, token)


def invitation_mail(
    db: Session,
    to: str,
    organization_name: str,
    role: str,
    inviter: Optional[str],
    token: str,
    expires_at: datetime,
) -> OutgoingMail:
    """Sent when someone is invited to an institution: the link opens the page to create the account.

    The token goes in the fragment, like the verify and reset links (see `link`). The markers say who invited, which
    institution, what the person will be there (admin or reader) and until when the link works.
    """
    values = {
        "institucion": organization_name,
        "invitador": f"{inviter} te invitó" if inviter else "Te invitaron",
        "rol": INVITATION_ROLE_TEXT["org_admin" if role == "org_admin" else "viewer"],
        "vence": expires_at.astimezone(timezone.utc).strftime("%d/%m/%Y"),
    }
    return _mail(db, "invitation", to, values, token)


def account_exists_mail(db: Session, user: User) -> OutgoingMail:
    """Sent when someone signs up with a mail that already has an account.

    The sign-up form answers the same either way (so nobody can tell which mails have an account); the
    owner of the address learns it here. It carries no token, only a link to the recovery page.
    """
    return _mail(db, "account_exists", user.email, {"usuario": user.username})


# What {rol} says in the invitation, by role. Fixed text: the role itself is not editable, only the words around it.
INVITATION_ROLE_TEXT = {
    "org_admin": "administrador de la institución (vas a poder agregar y administrar a sus usuarios)",
    "viewer": "usuario de la institución",
}


def preview_mail(key: str, draft: dict) -> OutgoingMail:
    """The mail `key` built from a DRAFT (not saved) and the example data, for the admin's preview. Sends nothing.

    It is built by the same `_build` as a real mail, so what the admin sees is what people get. The logo is an inline
    attachment (`cid:`) in a real mail, which a screen cannot show: here it points to the site's public image.
    """
    t = texts.render_texts(draft, texts.PLACEHOLDERS[key])
    button_path, fallback_path = _PAGES[key]
    token = "T" * 43 if key != "account_exists" else None
    mail = _build(
        "ana.perez@ejemplo.com.ar",
        t["subject"],
        t["heading"],
        t["paragraphs"],
        t["button"],
        link(button_path, token),
        t["footer"],
        fallback_path,
        t["fallback"],
    )
    html = mail.html.replace(f"cid:{LOGO_CID}", PREVIEW_LOGO_PATH)
    return OutgoingMail(to=mail.to, subject=mail.subject, text=mail.text, html=html)


# The site's own copy of the logo (relative: <base href> adds the prefix when the site is served under one).
PREVIEW_LOGO_PATH = "assets/images/logos/OHMC@3x.png"
