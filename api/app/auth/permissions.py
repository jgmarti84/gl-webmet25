# api/app/auth/permissions.py
"""Who may open which one-radar detail view (spec C). Functions flush; routers commit.

Only GET /permissions/me and the admin endpoints call this module. Data endpoints never do (decision C1): every
user keeps seeing every radar on the main map; the permission only opens radar.html.
"""

from typing import Iterable, List, Set

from sqlalchemy.orm import Session

from radar_db.models import PERMISSION_ALL, Organization, Permission, Radar, User

RADAR_DETAIL_VIEW = "radar.detail_view"


class PermissionRuleError(Exception):
    """A permission change that breaks a rule; the router turns it into this HTTP status."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def stored_radar_views(user: User) -> List[str]:
    """The user's own list as saved (radar codes, or ["*"]), sorted. Not filtered by detail_view_enabled."""
    return sorted(p.resource for p in user.permissions if p.action == RADAR_DETAIL_VIEW)


def stored_org_radar_views(org: Organization) -> List[str]:
    """The company's list as saved (radar codes, or ["*"]), sorted."""
    return sorted(p.resource for p in org.permissions if p.action == RADAR_DETAIL_VIEW)


def _enabled_radar_codes(db: Session) -> Set[str]:
    """Codes of the radars whose detail view is switched on (decision C2: the flag is always required)."""
    return {code for (code,) in db.query(Radar.code).filter(Radar.detail_view_enabled.is_(True)).all()}


def _expand(stored: Set[str], enabled: Set[str]) -> Set[str]:
    """A saved list turned into real codes: "*" means every enabled radar; otherwise keep the enabled ones."""
    return set(enabled) if PERMISSION_ALL in stored else stored & enabled


def effective_radar_views(db: Session, user: User) -> List[str]:
    """Radar codes whose detail view this user may open now (spec C §4), sorted.

    admin: every enabled view. No company: their own list. Company admin: the company's list. Company member:
    their own list intersected with the company's (decision C6: computed here, so a radar the company loses
    disappears for every member without touching their lists).
    """
    enabled = _enabled_radar_codes(db)
    if user.role == "admin":
        return sorted(enabled)
    own = _expand(set(stored_radar_views(user)), enabled)
    if user.organization is None:
        return sorted(own)
    company = _expand(set(stored_org_radar_views(user.organization)), enabled)
    if user.role == "org_admin":
        return sorted(company)
    return sorted(own & company)


def _wanted_resources(db: Session, resources: Iterable[str]) -> Set[str]:
    """Deduplicate, collapse to {"*"} when it is present, and reject codes that are not radars (422)."""
    wanted = set(resources)
    if PERMISSION_ALL in wanted:
        return {PERMISSION_ALL}
    known = {code for (code,) in db.query(Radar.code).filter(Radar.code.in_(wanted)).all()} if wanted else set()
    unknown = sorted(wanted - known)
    if unknown:
        raise PermissionRuleError(422, f"Radares inexistentes: {', '.join(unknown)}")
    return wanted


def _replace_rows(db: Session, rows: list, wanted: Set[str], granted_by: User) -> None:
    """Swap the detail-view rows of a user's or a company's `permissions` collection for `wanted`."""
    for permission in [p for p in rows if p.action == RADAR_DETAIL_VIEW]:
        rows.remove(permission)  # delete-orphan: the row is deleted
    # Deletes first: SQLAlchemy inserts before it deletes, and re-adding a code would break the unique constraint.
    db.flush()
    for resource in sorted(wanted):
        rows.append(Permission(action=RADAR_DETAIL_VIEW, resource=resource, granted_by=granted_by.id))
    db.flush()


def replace_user_radar_views(
    db: Session, user: User, resources: Iterable[str], granted_by: User, within_company: bool = False
) -> List[str]:
    """Replace the user's whole list (decision C16) and return it as stored.

    within_company=True is the company admin's case (decision C4): the new list must fit inside the company's
    list, otherwise PermissionRuleError(403). A company with "*" allows anything, "*" included.

    The user row is locked first (SELECT ... FOR UPDATE) and reloaded. Two admins saving the same user at the same
    moment would otherwise both delete the old rows and insert the new ones, and the second insert would break the
    unique constraint (a 500). With the lock the second one waits for the first to commit, then replaces that list
    with its own: the last save wins, and nobody gets an error.
    """
    db.refresh(user, with_for_update=True)
    wanted = _wanted_resources(db, resources)
    if within_company:
        company = set(stored_org_radar_views(user.organization)) if user.organization is not None else set()
        if PERMISSION_ALL not in company and not wanted <= company:
            raise PermissionRuleError(403, "Solo podés asignar vistas que tenga tu empresa")
    _replace_rows(db, user.permissions, wanted, granted_by)
    return stored_radar_views(user)


def replace_org_radar_views(db: Session, org: Organization, resources: Iterable[str], granted_by: User) -> List[str]:
    """Replace the company's whole list. Members keep their own lists; the intersection hides what was removed.

    The company row is locked first, for the same reason as the user row in replace_user_radar_views."""
    db.refresh(org, with_for_update=True)
    wanted = _wanted_resources(db, resources)
    _replace_rows(db, org.permissions, wanted, granted_by)
    return stored_org_radar_views(org)


def copy_company_views_to(db: Session, user: User, granted_by: User) -> None:
    """Give a company user the company's current list (decision C5: new members start with everything)."""
    _replace_rows(db, user.permissions, set(stored_org_radar_views(user.organization)), granted_by)


def delete_radar_permissions(db: Session, radar_code: str) -> None:
    """Remove every detail-view permission on a radar that is being deleted (same transaction as the delete).

    Covers the permissions of users and of companies: both name the radar by code."""
    db.query(Permission).filter(Permission.action == RADAR_DETAIL_VIEW, Permission.resource == radar_code).delete(
        synchronize_session=False
    )
