# api/app/routers/invitations.py
"""Invitations by mail to an institution (spec E).

Three routers: the general admin's (any institution), the institution admin's (its own institution, viewers only)
and the public one where the invited person opens the link and creates the account. The token is never in a URL: the
mail carries it in the fragment and the public endpoints take it in the body, so it stays out of the access logs.
"""

from typing import List, Optional, Union

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from radar_db import get_db
from radar_db.models import Invitation, User

from ..auth import invitations as service
from ..auth import service as auth_service
from ..auth.cookies import request_base_path, set_auth_cookies
from ..auth.dependencies import check_origin, get_current_user, require_admin, require_org_admin
from ..auth.google import GoogleIdentity, GoogleTokenError, GoogleVerifier, get_google_verifier
from ..auth.google_login import GoogleLoginError
from ..auth.security import create_access_token
from ..config import settings
from ..mail.service import Mailer, get_mailer
from ..schemas.auth import MeResponse
from ..schemas.invitations import (
    AcceptInvitation,
    AcceptInvitationGoogle,
    InvitationCreate,
    InvitationDetails,
    InvitationResponse,
    InvitationToken,
    OrgInvitationCreate,
)
from ..schemas.permissions import ToolsUpdate
from .auth import _client_info, _full_access_lifetime, _me
from .registration import _require_mail, _send_later

admin_router = APIRouter(
    prefix="/admin/invitations",
    tags=["Admin invitations"],
    dependencies=[Depends(require_admin), Depends(check_origin)],
)
org_router = APIRouter(prefix="/org/invitations", tags=["Company admin"], dependencies=[Depends(check_origin)])
public_router = APIRouter(prefix="/invitations", tags=["Invitations"], dependencies=[Depends(check_origin)])


def _response(invitation: Invitation, info=(False, None), show_leaves: bool = False) -> InvitationResponse:
    """The answer for one invitation. `info` is (the mail has an account, institution it would leave) from
    service.account_info; the second one is only given to the general admin (`show_leaves`)."""
    existing, leaves = info
    return InvitationResponse(
        existing_account=existing,
        leaves_organization=leaves if show_leaves else None,
        id=invitation.id,
        email=invitation.email,
        organization_id=invitation.organization_id,
        organization_name=invitation.organization.name,
        role=invitation.role,
        radar_views=invitation.radar_views,
        tools=ToolsUpdate(**invitation.tools) if invitation.tools else None,
        created_at=invitation.created_at,
        expires_at=invitation.expires_at,
    )


def _responses(db: Session, rows: List[Invitation], show_leaves: bool) -> List[InvitationResponse]:
    """A list of invitations, with the account info of all their mails worked out in one query."""
    info = service.account_info(db, rows)
    return [_response(row, info.get(row.id, (False, None)), show_leaves) for row in rows]


def _rule(exc: service.InvitationError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def _invite(
    db: Session,
    background: BackgroundTasks,
    mailer: Mailer,
    actor: User,
    organization_id: int,
    email: str,
    role: str,
    radar_views: Optional[List[str]],
    within_company: bool = False,
    tools: Optional[dict] = None,
) -> InvitationResponse:
    """Create the invitation, commit, and send the mail after the response (shared by both inviters).

    `within_company` is the institution admin's case: the views it picks must fit inside its institution's list."""
    _require_mail()
    try:
        invitation, mail = service.create_invitation(
            db, actor, organization_id, email, role, radar_views, within_company=within_company, tools=tools
        )
    except service.InvitationError as exc:
        raise _rule(exc)
    db.commit()
    _send_later(background, mailer, [mail])
    return _responses(db, [invitation], actor.role == "admin")[0]


def _renew(
    db: Session, background: BackgroundTasks, mailer: Mailer, actor: User, invitation_id: str, organization_id=None
) -> InvitationResponse:
    """Resend: a new link for the same person; the old one stops working."""
    _require_mail()
    try:
        old = service.get_pending(db, invitation_id, organization_id)
        invitation, mail = service.resend(db, actor, old)
    except service.InvitationError as exc:
        raise _rule(exc)
    db.commit()
    _send_later(background, mailer, [mail])
    return _responses(db, [invitation], actor.role == "admin")[0]


def _cancel(db: Session, invitation_id: str, organization_id=None) -> Response:
    try:
        service.cancel(db, service.get_pending(db, invitation_id, organization_id))
    except service.InvitationError as exc:
        raise _rule(exc)
    db.commit()
    return Response(status_code=204)


# --- the general admin ---------------------------------------------------------------------------------------


@admin_router.post("", response_model=InvitationResponse, status_code=201)
def admin_create(
    payload: InvitationCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
    mailer: Mailer = Depends(get_mailer),
) -> InvitationResponse:
    """Invite someone to any institution as its admin (org_admin) or as a viewer."""
    return _invite(
        db,
        background,
        mailer,
        actor,
        payload.organization_id,
        payload.email,
        payload.role,
        payload.radar_views,
        tools=payload.tools.model_dump(exclude_none=True) if payload.tools else None,
    )


@admin_router.get("", response_model=List[InvitationResponse])
def admin_list(organization_id: Optional[int] = None, db: Session = Depends(get_db)) -> List[InvitationResponse]:
    return _responses(db, service.pending_of(db, organization_id), True)


@admin_router.post("/{invitation_id}/resend", response_model=InvitationResponse)
def admin_resend(
    invitation_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    actor: User = Depends(require_admin),
    mailer: Mailer = Depends(get_mailer),
) -> InvitationResponse:
    return _renew(db, background, mailer, actor, invitation_id)


@admin_router.post("/{invitation_id}/cancel", status_code=204)
def admin_cancel(invitation_id: str, db: Session = Depends(get_db)) -> Response:
    return _cancel(db, invitation_id)


# --- the institution admin: its own institution, viewers only -------------------------------------------------


@org_router.post("", response_model=InvitationResponse, status_code=201)
def org_create(
    payload: OrgInvitationCreate,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    actor: User = Depends(require_org_admin),
    mailer: Mailer = Depends(get_mailer),
) -> InvitationResponse:
    """Invite a viewer to the caller's institution. Any institution or role in the body is ignored."""
    return _invite(
        db,
        background,
        mailer,
        actor,
        actor.organization_id,
        payload.email,
        "viewer",
        payload.radar_views,
        True,
        tools=payload.tools.model_dump(exclude_none=True) if payload.tools else None,
    )


@org_router.get("", response_model=List[InvitationResponse])
def org_list(db: Session = Depends(get_db), actor: User = Depends(require_org_admin)) -> List[InvitationResponse]:
    return _responses(db, service.pending_of(db, actor.organization_id), False)


@org_router.post("/{invitation_id}/resend", response_model=InvitationResponse)
def org_resend(
    invitation_id: str,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    actor: User = Depends(require_org_admin),
    mailer: Mailer = Depends(get_mailer),
) -> InvitationResponse:
    return _renew(db, background, mailer, actor, invitation_id, actor.organization_id)


@org_router.post("/{invitation_id}/cancel", status_code=204)
def org_cancel(invitation_id: str, db: Session = Depends(get_db), actor: User = Depends(require_org_admin)) -> Response:
    return _cancel(db, invitation_id, actor.organization_id)


# --- the invited person (no session) --------------------------------------------------------------------------


@public_router.post("/details", response_model=InvitationDetails)
def details(payload: InvitationToken, db: Session = Depends(get_db)) -> InvitationDetails:
    """What the page shows before the account is created: the institution, the mail and the role."""
    try:
        invitation = service.find_by_token(db, payload.token)
    except service.InvitationError as exc:
        raise _rule(exc)
    return InvitationDetails(
        organization_name=invitation.organization.name,
        email=invitation.email,
        role=invitation.role,
        google_available=settings.google_login_available,
        # Decides which screen the page shows: the login (the mail has an account) or the sign-up form. Only whoever has
        # the link gets this, and the server checks everything again when the person accepts.
        account_exists=service.account_info(db, [invitation])[invitation.id][0],
    )


def _open_session(db: Session, user: User, request: Request, response: Response) -> MeResponse:
    """Commit the new account and log it in: the same cookies as /auth/login, for the base path of the request."""
    user_agent, ip = _client_info(request)
    session, refresh_token = auth_service.create_session(db, user, user_agent=user_agent, ip=ip)
    db.commit()
    access_token = create_access_token(user.id, user.role, user.token_version)
    set_auth_cookies(response, access_token, refresh_token, session.expires_at, base_path=request_base_path(request))
    return _me(user, _full_access_lifetime())


@public_router.post("/accept", response_model=MeResponse)
def accept(
    payload: AcceptInvitation, request: Request, response: Response, db: Session = Depends(get_db)
) -> MeResponse:
    """Create the account from the form and log the person in. The link works once."""
    if settings.terms_required and not payload.accept_terms:
        raise HTTPException(status_code=422, detail="Tenés que aceptar los términos y la política de privacidad")
    try:
        user = service.accept_with_password(db, payload.token, payload.username, payload.password, payload.full_name)
    except service.InvitationError as exc:
        raise _rule(exc)
    return _open_session(db, user, request, response)


@public_router.post("/accept-google", response_model=MeResponse)
def accept_google(
    payload: AcceptInvitationGoogle,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    verifier: GoogleVerifier = Depends(get_google_verifier),
) -> Union[MeResponse, JSONResponse]:
    """Create the account with the Google identity of the browser's ID token. Google's mail must be the invited one."""
    if not settings.google_login_available:
        raise HTTPException(status_code=503, detail="Iniciar sesión con Google no está disponible por ahora")
    try:
        identity: GoogleIdentity = verifier.verify(payload.credential)
    except GoogleTokenError:
        raise HTTPException(status_code=401, detail="No pudimos verificar tu cuenta de Google")
    try:
        user = service.accept_with_google(db, payload.token, identity)
    except service.InvitationError as exc:
        raise _rule(exc)
    except GoogleLoginError as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "code": exc.code})
    return _open_session(db, user, request, response)


@public_router.post("/accept-existing", response_model=MeResponse)
def accept_existing(
    payload: InvitationToken,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MeResponse:
    """Join the institution with the account that is logged in: for a mail that already has an account.

    It needs a session AND the link: the account of the session must be the one of the invited mail (403 otherwise), so
    the link alone cannot enter anybody's account. It acts only on the account of the session. The rules are checked
    again here (see service.accept_existing) and, when it works, a fresh session replaces the old ones."""
    try:
        joined = service.accept_existing(db, user, payload.token)
    except service.InvitationError as exc:
        raise _rule(exc)
    return _open_session(db, joined, request, response)
