# api/app/routers/registration.py
"""Public registration, e-mail verification and password recovery (spec B).

Every endpoint is public (no session) and checks the request origin like the login does. The ones that can
send mail answer the same whether or not the account exists ("neutral"), and send the mail in the background
after the transaction is committed, so neither the answer nor its timing depends on the mail.
"""

from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from radar_db import get_db
from radar_db.accounts import AccountError, UsernameTakenError
from radar_db.passwords import PasswordPolicyError

from ..auth import registration
from ..auth.dependencies import check_origin
from ..auth.email_tokens import InvalidEmailToken
from ..config import settings
from ..mail.service import Mailer, OutgoingMail, get_mailer, send_safely
from ..schemas.registration import (
    ForgotPasswordRequest,
    IdentifierRequest,
    MessageResponse,
    OptionsResponse,
    RegisterRequest,
    ResetPasswordRequest,
    TokenRequest,
)

router = APIRouter(prefix="/auth", tags=["Registration"], dependencies=[Depends(check_origin)])

NEUTRAL = "Si los datos son correctos, te enviamos un mail para continuar. Revisá tu bandeja de entrada."
# One message for a link that is unknown, malformed, expired, already used or for another purpose.
INVALID_LINK = "El link no es válido o ya venció. Pedí uno nuevo."


def _require_mail() -> None:
    """503 when the SMTP settings are incomplete: the endpoint could not deliver what it promises."""
    if not settings.mail_configured:
        raise HTTPException(status_code=503, detail="El envío de mails no está disponible por ahora")


def _send_later(background: BackgroundTasks, mailer: Mailer, mails: List[OutgoingMail]) -> None:
    """Queue the mails to go out after the response; a failure is logged and never reaches the client."""
    for mail in mails:
        background.add_task(send_safely, mailer, mail)


@router.get("/options", response_model=OptionsResponse)
def options() -> OptionsResponse:
    """What the login page may offer (public)."""
    return OptionsResponse(
        registration=settings.registration_available,
        password_recovery=settings.mail_configured,
        terms_url=settings.terms_url or None,
        privacy_url=settings.privacy_url or None,
    )


@router.post("/register", status_code=202, response_model=MessageResponse)
def register(
    payload: RegisterRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    mailer: Mailer = Depends(get_mailer),
) -> MessageResponse:
    """Create a pending account. 202 for a new or an already-registered mail alike; 409 only for the username."""
    if not settings.registration_available:
        raise HTTPException(status_code=503, detail="El registro no está disponible por ahora")
    if payload.website.strip():
        return MessageResponse(detail=NEUTRAL)  # decoy filled: a bot; do nothing
    if not payload.accept_terms:
        raise HTTPException(status_code=422, detail="Tenés que aceptar los términos y la política de privacidad")
    try:
        mails = registration.register(db, username=payload.username, email=payload.email, password=payload.password)
        db.commit()
    except UsernameTakenError:
        raise HTTPException(status_code=409, detail="Ese usuario ya existe")
    except (AccountError, PasswordPolicyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except IntegrityError:
        # Two simultaneous registrations raced for the same username or mail and the database refused one.
        db.rollback()
        raise HTTPException(status_code=409, detail="No se pudo completar el registro. Probá de nuevo.")
    _send_later(background, mailer, mails)
    return MessageResponse(detail=NEUTRAL)


@router.post("/verify-email", status_code=204)
def verify_email(payload: TokenRequest, db: Session = Depends(get_db)) -> Response:
    """Redeem the link of the verification mail. The page that calls this opens from a static address."""
    _require_mail()
    try:
        registration.verify_email(db, payload.token)
    except InvalidEmailToken:
        raise HTTPException(status_code=400, detail=INVALID_LINK)
    db.commit()
    return Response(status_code=204)


@router.post("/resend-verification", status_code=202, response_model=MessageResponse)
def resend_verification(
    payload: IdentifierRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    mailer: Mailer = Depends(get_mailer),
) -> MessageResponse:
    """New verification mail for an unverified account; the answer is the same for any identifier."""
    _require_mail()
    mails = registration.resend_verification(db, payload.identifier)
    db.commit()
    _send_later(background, mailer, mails)
    return MessageResponse(detail=NEUTRAL)


@router.post("/forgot-password", status_code=202, response_model=MessageResponse)
def forgot_password(
    payload: ForgotPasswordRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    mailer: Mailer = Depends(get_mailer),
) -> MessageResponse:
    """Reset link by mail; the answer is the same whether or not the address has an account."""
    _require_mail()
    mails = registration.forgot_password(db, payload.email)
    db.commit()
    _send_later(background, mailer, mails)
    return MessageResponse(detail=NEUTRAL)


@router.post("/reset-password", status_code=204)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> Response:
    """Set a new password with the link of the reset mail. A weak password is a 422 and keeps the link usable."""
    _require_mail()
    try:
        registration.reset_password(db, payload.token, payload.password)
    except InvalidEmailToken:
        raise HTTPException(status_code=400, detail=INVALID_LINK)
    except PasswordPolicyError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    db.commit()
    return Response(status_code=204)
