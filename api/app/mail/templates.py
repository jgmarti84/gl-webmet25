# api/app/mail/templates.py
"""Bodies of the account mails (Spanish): plain text and HTML, values escaped."""

from html import escape
from typing import List, Optional

from radar_db.models import User

from ..config import settings
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


def verification_mail(user: User, token: str) -> OutgoingMail:
    """Sent after signing up: the link proves the person controls the address."""
    return _build(
        user.email,
        "Verificá tu mail - WebMet25",
        "Verificá tu mail",
        [
            f"Hola {user.username}, gracias por crear tu cuenta en WebMet25.",
            f"Para activarla, verificá tu mail. El link sirve una sola vez y vence en "
            f"{settings.email_verify_ttl_hours} horas.",
        ],
        "Verificar mi mail",
        link("/verify", token),
        "Si no creaste una cuenta, ignorá este mensaje.",
        # A new verification mail is asked for from the login page ("Reenviar mail de verificación").
        "/login",
        "Si el botón no funciona, entrá a",
    )


def reset_mail(user: User, token: str) -> OutgoingMail:
    """Sent by "forgot my password": the link opens the page to choose a new one."""
    return _build(
        user.email,
        "Recuperá tu contraseña - WebMet25",
        "Recuperá tu contraseña",
        [
            f"Hola {user.username}, recibimos un pedido para cambiar tu contraseña.",
            f"El link sirve una sola vez y vence en {settings.password_reset_ttl_minutes} minutos. "
            "Al cambiarla se cierran todas tus sesiones.",
        ],
        "Elegir una contraseña nueva",
        link("/reset", token),
        "Si no fuiste vos, ignorá este mensaje: tu contraseña no cambia.",
        "/forgot",
        "Si el botón no funciona, pedí un mail nuevo en",
    )


def account_exists_mail(user: User) -> OutgoingMail:
    """Sent when someone signs up with a mail that already has an account.

    The sign-up form answers the same either way (so nobody can tell which mails have an account); the
    owner of the address learns it here. It carries no token, only a link to the recovery page.
    """
    return _build(
        user.email,
        "Ya tenés una cuenta - WebMet25",
        "Ya tenés una cuenta",
        [
            f"Alguien intentó crear una cuenta con este mail, pero ya existe una con el usuario {user.username}.",
            "Si fuiste vos, podés entrar con ese usuario o recuperar tu contraseña.",
        ],
        "Recuperar mi contraseña",
        link("/forgot"),
        "Si no fuiste vos, ignorá este mensaje: no se hizo ningún cambio.",
        "/forgot",
        "Si el botón no funciona, entrá a",
    )
