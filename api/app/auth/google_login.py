# api/app/auth/google_login.py
"""What happens after Google vouched for a person: find their account, link it, or create it.

Functions flush; routers commit."""

import logging
import re
import secrets
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from radar_db.accounts import (
    create_user,
    get_user_by_email,
    get_user_by_username,
    normalize_email,
    normalize_full_name,
    set_password,
)
from radar_db.models import User

from .google import GoogleIdentity

logger = logging.getLogger("auth.google")

# How many numbered variants of a taken username are tried before giving up (ana.perez, ana.perez2, ...).
MAX_USERNAME_TRIES = 50
USERNAME_MAX = 32
USERNAME_MIN = 3


class GoogleLoginError(Exception):
    """The person cannot come in with Google. `code` lets the login page show the right message."""

    def __init__(self, status_code: int, detail: str, code: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.code = code


def _free_username(db: Session, email: str) -> str:
    """A username built from the part of the mail before the "@": lower case, characters a username cannot have
    turned into dots, cut to fit, completed when too short, and numbered when someone already has it."""
    local = email.split("@", 1)[0].lower()
    base = re.sub(r"[^a-z0-9._-]+", ".", local).strip(".-_") or "usuario"
    if len(base) < USERNAME_MIN:
        base = (base + "user")[:USERNAME_MAX]
    base = base[: USERNAME_MAX - 4]  # leaves room for a number
    candidate, number = base, 1
    while get_user_by_username(db, candidate) is not None:
        number += 1
        if number > MAX_USERNAME_TRIES:
            # Practically unreachable; a random tail still gives a free name instead of an error.
            candidate = f"{base}.{secrets.token_hex(3)}"[:USERNAME_MAX]
            break
        candidate = f"{base}{number}"
    return candidate


def _unusable_password() -> str:
    """A long random password nobody knows: the account only enters through Google (or after a password recovery)."""
    return secrets.token_urlsafe(32)


def sign_in(db: Session, identity: GoogleIdentity, now: Optional[datetime] = None) -> User:
    """Return the user this Google identity is, ready to get a session. Rules:

    * Google must have verified the mail.
    * Found by the Google "sub" first (the mail may have changed), else by the mail.
    * Administrators never come in this way, and deactivated accounts do not either.
    * A mail already linked to ANOTHER Google account is refused (the mail was reused).
    * Linking an account that was never verified (someone signed up with this mail and chose a password) drops that
      password and closes its sessions: whoever set it does not own the mailbox, the Google user does.
    * With no account, a viewer is created with the mail already verified.
    """
    now = now or datetime.now(timezone.utc)
    if not identity.email_verified:
        raise GoogleLoginError(
            403, "Google no confirmó tu mail, no podemos usarlo para entrar", "google_email_unverified"
        )
    email = normalize_email(identity.email)

    user = db.query(User).filter(User.google_sub == identity.sub).one_or_none()
    if user is None:
        user = get_user_by_email(db, email)

    if user is None:
        user = create_user(
            db,
            username=_free_username(db, email),
            password=_unusable_password(),
            role="viewer",
            full_name=normalize_full_name(identity.name),
            email=email,
            email_verified=True,
            google_sub=identity.sub,
        )
        logger.info("google signup user=%s", user.id)
    else:
        _check_may_come_in(user, identity)
        _link(db, user, identity, now)

    user.last_login_at = now
    db.flush()
    return user


def _check_may_come_in(user: User, identity: GoogleIdentity) -> None:
    if user.role == "admin":
        raise GoogleLoginError(403, "Las cuentas de administrador entran con usuario y contraseña", "admin_no_google")
    if not user.is_active:
        raise GoogleLoginError(403, "Tu cuenta está desactivada", "account_disabled")
    if user.google_sub is not None and user.google_sub != identity.sub:
        raise GoogleLoginError(403, "Ese mail está enlazado a otra cuenta de Google", "google_account_mismatch")


def _link(db: Session, user: User, identity: GoogleIdentity, now: datetime) -> None:
    if user.google_sub is None:
        user.google_sub = identity.sub
        logger.info("google linked user=%s", user.id)
    if user.email_verified_at is None:
        # The mail is confirmed now (by Google), but the password on this account was chosen by whoever signed up.
        user.email_verified_at = now
        # set_password also closes every session of the account.
        set_password(db, user, _unusable_password(), now, reason="google_link")
