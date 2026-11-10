# api/app/routers/mail_templates.py
"""The text of the mails the app sends, editable by the GENERAL ADMIN only (spec F).

Every route needs a session with the admin role (401 without a session, 403 for an institution admin or a viewer) and
refuses requests from a foreign origin. The mail key is one of four fixed names (any other value is a 422 before the
database is touched). Only the text can change: the layout, the button and its link live in api/app/mail/templates.py.
"""

from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from radar_db import get_db
from radar_db.models import MailTemplate, User

from ..auth.dependencies import check_origin, require_admin
from ..mail import texts
from ..mail.templates import preview_mail
from ..schemas.mail_templates import MailPreviewResponse, MailTemplateResponse, MailTextsBody

router = APIRouter(
    prefix="/admin/mail-templates",
    tags=["Admin mail texts"],
    dependencies=[Depends(require_admin), Depends(check_origin)],
)

# The four mails, as a type: FastAPI answers 422 for any other value in the URL.
MailKey = Literal["verify_email", "reset_password", "account_exists", "invitation"]


def _item(db: Session, key: str) -> MailTemplateResponse:
    """The mail `key` as the screen shows it (the text in use, the original, the markers, who changed it and when)."""
    row = db.query(MailTemplate).filter(MailTemplate.key == key).one_or_none()
    editor = db.get(User, row.updated_by) if row is not None and row.updated_by else None
    return MailTemplateResponse(
        key=key,
        title=texts.TITLES[key],
        customized=row is not None,
        texts=texts.stored_texts(db, key) or texts.DEFAULT_TEXTS[key],
        defaults=texts.DEFAULT_TEXTS[key],
        placeholders=texts.placeholder_list(key),
        updated_at=row.updated_at if row is not None else None,
        updated_by_username=editor.username if editor is not None else None,
    )


def _refuse(error: texts.MailTextError) -> HTTPException:
    """A text that cannot be saved: 422 with the message in Spanish (never a 500)."""
    return HTTPException(status_code=error.status_code, detail=error.detail)


@router.get("", response_model=List[MailTemplateResponse])
def list_mail_templates(db: Session = Depends(get_db)) -> List[MailTemplateResponse]:
    """The four mails with their text in use, their original text and the markers each one accepts."""
    return [_item(db, key) for key in texts.KEYS]


@router.put("/{key}", response_model=MailTemplateResponse)
def save_mail_template(
    key: MailKey, body: MailTextsBody, db: Session = Depends(get_db), actor: User = Depends(require_admin)
):
    """Save the text of a mail (replaces the previous customization). Nothing is saved when any text is refused."""
    try:
        clean = texts.validate_texts(key, body.model_dump())
    except texts.MailTextError as exc:
        raise _refuse(exc)
    texts.save_texts(db, actor, key, clean)
    db.commit()
    return _item(db, key)


@router.delete("/{key}", status_code=204)
def restore_mail_template(
    key: MailKey, db: Session = Depends(get_db), actor: User = Depends(require_admin)
) -> Response:
    """Go back to the original text of the mail. A mail that was never customized is not an error."""
    texts.restore(db, actor, key)
    db.commit()
    return Response(status_code=204)


@router.post("/{key}/preview", response_model=MailPreviewResponse)
def preview_mail_template(key: MailKey, body: MailTextsBody):
    """The mail built from a draft and example data, as HTML. It sends nothing and saves nothing."""
    try:
        clean = texts.validate_texts(key, body.model_dump())
    except texts.MailTextError as exc:
        raise _refuse(exc)
    mail = preview_mail(key, clean)
    return MailPreviewResponse(subject=mail.subject, html=mail.html)
