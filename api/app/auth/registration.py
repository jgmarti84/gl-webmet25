# api/app/auth/registration.py
"""Public registration, e-mail verification and password recovery.

Functions flush; routers commit. The ones that can send mail return the mails to send: the router
sends them in the background after committing, so the response never depends on them.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from radar_db.accounts import (
    AccountError,
    UsernameTakenError,
    create_user,
    find_by_identifier,
    get_user_by_email,
    get_user_by_username,
    normalize_email,
    normalize_full_name,
    set_password,
    validate_username,
)
from radar_db.models import User
from radar_db.passwords import hash_password, validate_password

from ..config import settings
from ..mail.service import OutgoingMail
from ..mail.templates import account_exists_mail, reset_mail, verification_mail
from .email_tokens import (
    PURPOSE_RESET,
    PURPOSE_VERIFY,
    cancel_open_tokens,
    find_valid_token,
    issue_token,
    may_send_mail,
    record_notice,
)


def _now(now: Optional[datetime]) -> datetime:
    """The `now` argument exists so tests can move the clock; production passes nothing."""
    return now or datetime.now(timezone.utc)


def _verification(db: Session, user: User, now: datetime) -> OutgoingMail:
    """A fresh verification link for the user (the previous one stops working) wrapped in its mail."""
    token = issue_token(db, user, PURPOSE_VERIFY, timedelta(hours=settings.email_verify_ttl_hours), now)
    return verification_mail(user, token)


def _link_still_valid(user: User, now: datetime) -> bool:
    """True for an unverified account created less than EMAIL_VERIFY_TTL_HOURS ago.

    Its verification link may still work, so the account is protected from replacement. A verified account
    is never "pending", so it answers False here (verified accounts are handled by their own rules).
    """
    if user.email_verified_at is not None:
        return False
    return now - user.created_at < timedelta(hours=settings.email_verify_ttl_hours)


def register(
    db: Session,
    *,
    username: str,
    email: str,
    password: str,
    full_name: Optional[str] = None,
    terms_accepted: bool = True,
    now: Optional[datetime] = None,
) -> List[OutgoingMail]:
    """Create a pending viewer. A mail that already has a verified account gets a notice instead (neutral).

    `full_name` is the optional "Nombre y apellido" of the form: it is only used when the new account is created
    (rule 5 below); in every other path it is ignored, like the rest of the fields.
    `terms_accepted` says whether the person accepted terms: it stamps users.terms_accepted_at, and is False when
    the sign-up does not ask for any (TERMS_REQUIRED off), so no consent is recorded that was never given.

    Order of the rules (spec 4.1):
      1. mail of a verified account -> notice mail to its owner (neutral answer);
      2. mail of an unverified account whose link is still valid -> no replacement, a new link for that account;
      3. username of a verified account, or of an unverified one whose link is still valid -> UsernameTakenError;
      4. unverified accounts with that mail or username (all expired by now) are replaced;
      5. the new account is created.
    Returns the mails to send ([] when a cap says to send nothing: the caller answers the same either way).
    """
    now = _now(now)
    username = validate_username(username)
    address = normalize_email(email)
    if address is None:
        raise AccountError("Falta el mail")
    validate_password(password, username)
    # Hashed once in every path, so the response time does not say whether the mail has an account.
    password_hash = hash_password(password)

    holder = get_user_by_email(db, address)
    if holder is not None and holder.email_verified_at is not None:
        # Nobody can learn that this mail has an account: the answer is the same as for a new mail. The owner
        # is told by mail instead, within the per-account caps (record_notice is what counts those mails).
        if not may_send_mail(db, holder, now):
            return []
        record_notice(db, holder, now)
        return [account_exists_mail(holder)]

    # An unverified account is protected while its verification link is still valid (the person may be about to
    # click it). Replacing it earlier would let anyone push a pending person out, and would also delete the
    # account's rows in email_tokens, which restarts its mail caps: repeating a registration would then flood
    # the mailbox of the address with verification mails.
    if holder is not None and _link_still_valid(holder, now):
        # Same mail, pending: answer neutrally and send a new link to the account that already exists
        # (still within its per-account caps). The username and password typed now are not used.
        if not may_send_mail(db, holder, now):
            return []
        return [_verification(db, holder, now)]

    owner = get_user_by_username(db, username)
    if owner is not None and (owner.email_verified_at is not None or _link_still_valid(owner, now)):
        raise UsernameTakenError(f"El usuario '{username}' ya existe")

    # What is left are unverified accounts whose link already expired: nothing is lost by replacing them.
    # Accounts made by an admin or the CLI are verified from the start, so this can never delete one of those.
    stale = (
        db.query(User)
        .filter(User.email_verified_at.is_(None), or_(User.email == address, User.username == username))
        .all()
    )
    for old in stale:
        db.delete(old)
    db.flush()

    user = create_user(
        db,
        username=username,
        password=password,
        role="viewer",
        full_name=normalize_full_name(full_name),
        email=address,
        email_verified=False,
        terms_accepted=terms_accepted,
        password_hash=password_hash,
    )
    # Same clock as the rest of the flow (the column default is the database clock); the age rule reads it.
    user.created_at = now
    db.flush()
    return [_verification(db, user, now)]


def verify_email(db: Session, token: str, now: Optional[datetime] = None) -> None:
    """Redeem a verification link: the account can log in from now on. Raises InvalidEmailToken."""
    now = _now(now)
    row = find_valid_token(db, token, PURPOSE_VERIFY, now)
    row.used_at = now
    if row.user.email_verified_at is None:
        row.user.email_verified_at = now
    db.flush()


def resend_verification(db: Session, identifier: str, now: Optional[datetime] = None) -> List[OutgoingMail]:
    """New verification mail for an unverified account found by mail or username; [] for anything else."""
    now = _now(now)
    user = find_by_identifier(db, identifier)
    if user is None or user.email_verified_at is not None or not user.email:
        return []
    if not may_send_mail(db, user, now):
        return []
    return [_verification(db, user, now)]


def forgot_password(db: Session, email: str, now: Optional[datetime] = None) -> List[OutgoingMail]:
    """Reset mail for an active account with that mail; [] for unknown, inactive or capped accounts.

    An account that never verified its mail gets the verification mail instead.
    """
    now = _now(now)
    user = get_user_by_email(db, email)
    if user is None or not user.is_active:
        return []
    if not may_send_mail(db, user, now):
        return []
    if user.email_verified_at is None:
        return [_verification(db, user, now)]
    token = issue_token(db, user, PURPOSE_RESET, timedelta(minutes=settings.password_reset_ttl_minutes), now)
    return [reset_mail(user, token)]


def reset_password(db: Session, token: str, new_password: str, now: Optional[datetime] = None) -> None:
    """New password for the owner of the link. The token is only spent when the password is accepted."""
    now = _now(now)
    row = find_valid_token(db, token, PURPOSE_RESET, now)
    user = row.user
    validate_password(new_password, user.username)
    row.used_at = now
    cancel_open_tokens(db, user, PURPOSE_RESET, now)
    # The user closes their own sessions: record it as such, not as an admin action.
    set_password(db, user, new_password, now, reason="password_reset")
    if user.email_verified_at is None:
        user.email_verified_at = now  # opening the link proves control of the mailbox
    db.flush()
