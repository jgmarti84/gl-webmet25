# api/app/mail/texts.py
"""The editable TEXT of the mails (spec F): defaults, markers, validation, rendering and the saved overrides.

Only text is editable. The layout (logo, colors, the button with its link, the no-reply notice) stays in
templates.py. A mail has a row in `mail_templates` only when the general admin customized it; without a row the
default text below is used, so a fresh deploy changes no mail.

Why it is safe to let an admin write these texts:
* The text is only ever PLAIN TEXT: templates.py escapes every value when it builds the HTML.
* Markers like {usuario} are replaced by a regex and a per-mail whitelist. There is no template engine, no
  str.format and no eval, so nothing in the text is ever executed. A marker that looks right but that the mail does not
  have is refused when saving (a typo must never reach a real mail); any other braces stay as literal text.
* One-line fields (subject, heading, button...) cannot contain line breaks or other control characters, which closes
  header injection in the subject. The values that replace the markers are cleaned the same way.
* The database is only reached through the ORM with bound parameters, and the key is one of four fixed names.
"""

import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from radar_db.models import MailTemplate, User

logger = logging.getLogger(__name__)

KEYS = ("verify_email", "reset_password", "account_exists", "invitation")
FIELDS = ("subject", "heading", "body", "button", "footer", "fallback")
# Longest text of each field (the same numbers as the CHECK constraints of the table).
LIMITS = {"subject": 150, "heading": 120, "body": 2000, "button": 40, "footer": 400, "fallback": 200}
MAX_PARAGRAPHS = 8

# A marker is "{" + lower case letters and "_" + "}". Anything else with braces ({}, {{7*7}}, {0}) is plain text.
MARKER_RE = re.compile(r"\{([a-z_]+)\}")

TITLES = {
    "verify_email": "Verificación de mail",
    "reset_password": "Recuperar contraseña",
    "account_exists": "Ya tenés una cuenta",
    "invitation": "Invitación a una institución",
}

# What each mail may use: marker name -> the example the preview shows.
PLACEHOLDERS: Dict[str, Dict[str, str]] = {
    "verify_email": {"usuario": "ana.perez", "horas": "24"},
    "reset_password": {"usuario": "ana.perez", "minutos": "60"},
    "account_exists": {"usuario": "ana.perez"},
    "invitation": {
        "institucion": "EPEC",
        "invitador": "Laura Gómez te invitó",
        "rol": "administrador de la institución (vas a poder agregar y administrar a sus usuarios)",
        "vence": "12/11/2026",
    },
}

# The texts every mail has until somebody customizes it (the ones that used to be written in templates.py).
DEFAULT_TEXTS: Dict[str, Dict[str, str]] = {
    "verify_email": {
        "subject": "Verificá tu mail - WebMet25",
        "heading": "Verificá tu mail",
        "body": (
            "Hola {usuario}, gracias por crear tu cuenta en WebMet25.\n\n"
            "Para activarla, verificá tu mail. El link sirve una sola vez y vence en {horas} horas."
        ),
        "button": "Verificar mi mail",
        "footer": "Si no creaste una cuenta, ignorá este mensaje.",
        "fallback": "Si el botón no funciona, entrá a",
    },
    "reset_password": {
        "subject": "Recuperá tu contraseña - WebMet25",
        "heading": "Recuperá tu contraseña",
        "body": (
            "Hola {usuario}, recibimos un pedido para cambiar tu contraseña.\n\n"
            "El link sirve una sola vez y vence en {minutos} minutos. Al cambiarla se cierran todas tus sesiones."
        ),
        "button": "Elegir una contraseña nueva",
        "footer": "Si no fuiste vos, ignorá este mensaje: tu contraseña no cambia.",
        "fallback": "Si el botón no funciona, pedí un mail nuevo en",
    },
    "account_exists": {
        "subject": "Ya tenés una cuenta - WebMet25",
        "heading": "Ya tenés una cuenta",
        "body": (
            "Alguien intentó crear una cuenta con este mail, pero ya existe una con el usuario {usuario}.\n\n"
            "Si fuiste vos, podés entrar con ese usuario o recuperar tu contraseña."
        ),
        "button": "Recuperar mi contraseña",
        "footer": "Si no fuiste vos, ignorá este mensaje: no se hizo ningún cambio.",
        "fallback": "Si el botón no funciona, entrá a",
    },
    "invitation": {
        "subject": "Te invitaron a {institucion} en WebMet25",
        "heading": "Te invitaron a {institucion}",
        "body": (
            "{invitador} a unirte a {institucion} en WebMet25 como {rol}.\n\n"
            "Para crear tu cuenta (con una contraseña o con Google) abrí el link. "
            "Sirve una sola vez y vence el {vence}."
        ),
        "button": "Aceptar la invitación",
        "footer": "Si no esperabas esta invitación, ignorá este mensaje: no se crea ninguna cuenta.",
        "fallback": "Si el botón no funciona, pedile a quien te invitó que te envíe una invitación nueva. Sitio:",
    },
}


class MailTextError(Exception):
    """A text that cannot be saved; the router turns it into this HTTP status (always a 4xx, never a 500)."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _has_control_chars(text: str, allow_newline: bool = False) -> bool:
    """True when the text has a control character (line breaks, tabs, bell, NUL...). `\\n` can be allowed (body)."""
    return any(unicodedata.category(ch).startswith("C") and not (allow_newline and ch == "\n") for ch in text)


def validate_texts(key: str, texts: Dict[str, str]) -> Dict[str, str]:
    """Check and clean the six texts of a mail (422 with a message in Spanish when one is not acceptable).

    Spaces at the ends are trimmed. One-line fields cannot have line breaks. The body is split into paragraphs on blank
    lines (1 to 8). Every marker must be one the mail accepts. Returns the cleaned texts, ready to save.
    """
    allowed = PLACEHOLDERS[key]
    clean: Dict[str, str] = {}
    for field in FIELDS:
        value = texts.get(field)
        if not isinstance(value, str):
            raise MailTextError(422, f"Falta el texto de {field}")
        value = value.replace("\r\n", "\n").replace("\r", "\n") if field == "body" else value
        value = value.strip()
        if not value:
            raise MailTextError(422, f"El texto de {field} no puede estar vacío")
        if len(value) > LIMITS[field]:
            raise MailTextError(422, f"El texto de {field} puede tener hasta {LIMITS[field]} caracteres")
        if _has_control_chars(value, allow_newline=field == "body"):
            raise MailTextError(422, f"El texto de {field} no puede tener saltos de línea ni caracteres de control")
        if field == "body":
            paragraphs = [p.strip() for p in re.split(r"\n\s*\n", value) if p.strip()]
            if not 1 <= len(paragraphs) <= MAX_PARAGRAPHS:
                raise MailTextError(422, f"El cuerpo puede tener de 1 a {MAX_PARAGRAPHS} párrafos")
            value = "\n\n".join(" ".join(p.split()) for p in paragraphs)
        for name in MARKER_RE.findall(value):
            if name not in allowed:
                available = ", ".join("{" + n + "}" for n in allowed)
                raise MailTextError(422, f"La marca {{{name}}} no existe en este mail. Podés usar: {available}")
        clean[field] = value
    return clean


def _clean_value(value: object) -> str:
    """A value that replaces a marker: control characters (a line break in an institution name) become spaces."""
    text = "".join(" " if unicodedata.category(ch).startswith("C") else ch for ch in str(value))
    return " ".join(text.split())


def render(text: str, values: Dict[str, object]) -> str:
    """Replace the markers of `text` with `values`. Unknown markers and other braces are left as they are."""
    return MARKER_RE.sub(lambda m: _clean_value(values[m.group(1)]) if m.group(1) in values else m.group(0), text)


def render_texts(texts: Dict[str, str], values: Dict[str, object]) -> Dict[str, object]:
    """The six texts with the markers replaced; the body comes back as a list of paragraphs, as templates.py needs."""
    rendered: Dict[str, object] = {field: render(texts[field], values) for field in FIELDS if field != "body"}
    rendered["paragraphs"] = [render(p, values) for p in texts["body"].split("\n\n") if p.strip()]
    return rendered


# --- what is saved ----------------------------------------------------------------------------------------------


def stored_texts(db: Session, key: str) -> Optional[Dict[str, str]]:
    """The customized texts of a mail, or None when it was never customized."""
    row = db.query(MailTemplate).filter(MailTemplate.key == key).one_or_none()
    return None if row is None else {field: getattr(row, field) for field in FIELDS}


def get_texts(db: Session, key: str) -> Dict[str, str]:
    """The texts to send: the customized ones, or the default ones.

    A failure to read the table never stops a mail (someone could be signing up or recovering a password): it is
    logged and the default text is used. The read runs in a savepoint so a database error does not leave the caller's
    transaction aborted.
    """
    try:
        with db.begin_nested():
            stored = stored_texts(db, key)
    except SQLAlchemyError:
        logger.exception("could not read the saved text of the mail %s: using the default text", key)
        return DEFAULT_TEXTS[key]
    return stored or DEFAULT_TEXTS[key]


def save_texts(db: Session, actor: User, key: str, texts: Dict[str, str]) -> MailTemplate:
    """Save (create or replace) the customized texts of a mail. `texts` must come from validate_texts."""
    row = db.query(MailTemplate).filter(MailTemplate.key == key).one_or_none()
    if row is None:
        row = MailTemplate(key=key)
        db.add(row)
    for field in FIELDS:
        setattr(row, field, texts[field])
    row.updated_by = actor.id
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
    logger.info("mail text saved key=%s by=%s", key, actor.id)
    return row


def restore(db: Session, actor: User, key: str) -> None:
    """Delete the customization: the mail goes back to its default text. Nothing to delete is not an error."""
    deleted = db.query(MailTemplate).filter(MailTemplate.key == key).delete(synchronize_session=False)
    db.flush()
    if deleted:
        logger.info("mail text restored key=%s by=%s", key, actor.id)


def placeholder_list(key: str) -> List[Dict[str, str]]:
    """The markers of a mail with the example the preview uses, for the admin screen."""
    return [{"name": name, "example": example} for name, example in PLACEHOLDERS[key].items()]
