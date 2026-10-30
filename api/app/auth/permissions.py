# api/app/auth/permissions.py
"""Who may open which one-radar detail view (spec C). Functions flush; routers commit.

Only GET /permissions/me and the admin endpoints call this module. Data endpoints never do (decision C1): every
user keeps seeing every radar on the main map; the permission only opens radar.html.
"""

from typing import Iterable, List, Set

from sqlalchemy.orm import Session

from radar_db.models import PERMISSION_ALL, Permission, Radar, User

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


def _enabled_radar_codes(db: Session) -> Set[str]:
    """Codes of the radars whose detail view is switched on (decision C2: the flag is always required)."""
    return {code for (code,) in db.query(Radar.code).filter(Radar.detail_view_enabled.is_(True)).all()}


def effective_radar_views(db: Session, user: User) -> List[str]:
    """Radar codes whose detail view this user may open now: wildcard expanded, view flag applied, sorted.

    The admin sees every enabled view. Anybody else sees the intersection of their list with the enabled radars;
    "*" means all of them, including radars created after the grant (decision C3).
    """
    enabled = _enabled_radar_codes(db)
    if user.role == "admin":
        return sorted(enabled)
    stored = set(stored_radar_views(user))
    if PERMISSION_ALL in stored:
        return sorted(enabled)
    return sorted(stored & enabled)


def replace_user_radar_views(db: Session, user: User, resources: Iterable[str], granted_by: User) -> List[str]:
    """Replace the user's whole list of detail views (decision C16) and return it as stored.

    Duplicates collapse, and a list containing "*" is stored as just "*". Every code must be an existing radar
    (with or without its view enabled), otherwise PermissionRuleError(422) and nothing changes.

    The user row is locked first (SELECT ... FOR UPDATE) and reloaded. Two admins saving the same user at the same
    moment would otherwise both delete the old rows and insert the new ones, and the second insert would break the
    unique constraint (a 500). With the lock the second one waits for the first to commit, then replaces that list
    with its own: the last save wins, and nobody gets an error.
    """
    db.refresh(user, with_for_update=True)
    wanted = set(resources)
    if PERMISSION_ALL in wanted:
        wanted = {PERMISSION_ALL}
    else:
        known = {code for (code,) in db.query(Radar.code).filter(Radar.code.in_(wanted)).all()} if wanted else set()
        unknown = sorted(wanted - known)
        if unknown:
            raise PermissionRuleError(422, f"Radares inexistentes: {', '.join(unknown)}")

    for permission in [p for p in user.permissions if p.action == RADAR_DETAIL_VIEW]:
        user.permissions.remove(permission)  # delete-orphan: the row is deleted
    # Flush the deletes first: SQLAlchemy inserts before it deletes, and re-adding a code that was already there
    # would break the unique constraint.
    db.flush()
    for resource in sorted(wanted):
        user.permissions.append(Permission(action=RADAR_DETAIL_VIEW, resource=resource, granted_by=granted_by.id))
    db.flush()
    return stored_radar_views(user)


def delete_radar_permissions(db: Session, radar_code: str) -> None:
    """Remove every detail-view permission on a radar that is being deleted (same transaction as the delete)."""
    db.query(Permission).filter(Permission.action == RADAR_DETAIL_VIEW, Permission.resource == radar_code).delete(
        synchronize_session=False
    )
