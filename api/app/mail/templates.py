# api/app/mail/templates.py
"""Bodies of the account mails (Spanish): plain text and HTML, values escaped."""

from html import escape
from typing import List, Optional

from radar_db.models import User

from ..config import settings
from .service import OutgoingMail


def link(path: str, token: Optional[str] = None) -> str:
    """Absolute link to a page of the site. rstrip avoids "//verify" when PUBLIC_BASE_URL ends with a slash."""
    base = settings.public_base_url.rstrip("/")
    return f"{base}{path}" + (f"?token={token}" if token else "")


def _build(to: str, subject: str, heading: str, lines: List[str], action: str, url: str, footer: str) -> OutgoingMail:
    """Same layout for every mail: heading, paragraphs, one button/link and a footer.

    Every value goes through escape() in the HTML version, so a username like "<script>" cannot inject markup.
    """
    text = "\n\n".join([heading, *lines, f"{action}: {url}", footer])
    paragraphs = "".join(f"<p>{escape(line)}</p>" for line in lines)
    html = (
        '<div style="font-family:Segoe UI,Arial,sans-serif;max-width:480px;margin:0 auto;color:#1e293b">'
        f'<h2 style="color:#0b1b3d">{escape(heading)}</h2>{paragraphs}'
        f'<p><a href="{escape(url, quote=True)}" style="display:inline-block;padding:12px 20px;'
        'background:#12306b;color:#ffffff;border-radius:6px;text-decoration:none;font-weight:600">'
        f"{escape(action)}</a></p>"
        '<p style="font-size:13px;color:#5b6b82">Si el botón no funciona, copiá este link en el navegador:<br>'
        f"{escape(url)}</p>"
        f'<p style="font-size:13px;color:#5b6b82">{escape(footer)}</p></div>'
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
    )
