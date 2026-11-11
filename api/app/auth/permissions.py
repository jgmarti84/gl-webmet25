# api/app/auth/permissions.py
"""Who may open which one-radar detail view, and who has which tool (the storm tracking tool). Functions flush;
routers commit.

Radar views are lists of radar codes; tools are yes/no (one row with resource "*" means "has it"). Both live in the
permissions table and follow the same rules: a member of an institution has what it was given AND what the
institution has (worked out when read, so taking something from an institution takes it from every member at once),
and an institution admin can only hand out what its institution has.

The map's data endpoints never call this module: every user sees every radar on the main map. Views decide who opens
radar.html; the tracking tool is enforced by nginx, which asks /auth/check before letting a request reach the service.
"""

from typing import Iterable, List, Optional, Set

from sqlalchemy.orm import Session

from radar_db.models import PERMISSION_ALL, Organization, Permission, Radar, User

RADAR_DETAIL_VIEW = "radar.detail_view"
TOOL_TRACKING = "tool.tracking"
# The tools the API knows, by the name the frontend uses ("tracking") and the permission action behind it.
TOOLS = {"tracking": TOOL_TRACKING}


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
    """Codes of the radars whose detail view is switched on (a view needs its flag switched on)."""
    return {code for (code,) in db.query(Radar.code).filter(Radar.detail_view_enabled.is_(True)).all()}


def _expand(stored: Set[str], enabled: Set[str]) -> Set[str]:
    """A saved list turned into real codes: "*" means every enabled radar; otherwise keep the enabled ones."""
    return set(enabled) if PERMISSION_ALL in stored else stored & enabled


def effective_radar_views(db: Session, user: User) -> List[str]:
    """Radar codes whose detail view this user may open now, sorted.

    admin: every enabled view. No company: their own list. Company admin: the company's list. Company member:
    their own list intersected with the company's (computed here, so a radar the company loses
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


def _replace_rows(db: Session, rows: list, wanted: Set[str], granted_by: User, action: str = RADAR_DETAIL_VIEW) -> None:
    """Swap the rows of one `action` in a user's or an institution's `permissions` collection for `wanted`."""
    for permission in [p for p in rows if p.action == action]:
        rows.remove(permission)  # delete-orphan: the row is deleted
    # Deletes first: SQLAlchemy inserts before it deletes, and re-adding a row would break the unique constraint.
    db.flush()
    for resource in sorted(wanted):
        rows.append(Permission(action=action, resource=resource, granted_by=granted_by.id))
    db.flush()


def ensure_within_org(org: Optional[Organization], wanted: Set[str]) -> None:
    """A company admin may only give views the company has: 403 when `wanted` goes beyond its list.

    A company with "*" allows anything, "*" included. No company (None) has no views to give. Used when a company
    admin sets a member's views and when it invites someone (the invitation carries the views the person will start
    with, so they must be checked when the invitation is made, not only when the account exists).
    """
    company = set(stored_org_radar_views(org)) if org is not None else set()
    if PERMISSION_ALL not in company and not wanted <= company:
        raise PermissionRuleError(403, "Solo podés asignar vistas que tenga tu institución")


def replace_user_radar_views(
    db: Session, user: User, resources: Iterable[str], granted_by: User, within_company: bool = False
) -> List[str]:
    """Replace the user's whole list and return it as stored.

    within_company=True is the company admin's case: the new list must fit inside the company's
    list, otherwise PermissionRuleError(403). A company with "*" allows anything, "*" included.

    The user row is locked first (SELECT ... FOR UPDATE) and reloaded. Two admins saving the same user at the same
    moment would otherwise both delete the old rows and insert the new ones, and the second insert would break the
    unique constraint (a 500). With the lock the second one waits for the first to commit, then replaces that list
    with its own: the last save wins, and nobody gets an error.
    """
    db.refresh(user, with_for_update=True)
    wanted = _wanted_resources(db, resources)
    if within_company:
        ensure_within_org(user.organization, wanted)
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
    """Give an institution member the institution's current radar views and tools: a new member (or one that moves in)
    starts with everything the institution has."""
    _replace_rows(db, user.permissions, set(stored_org_radar_views(user.organization)), granted_by)
    copy_company_tools_to(db, user, granted_by)


def stored_tool(owner, action: str) -> bool:
    """True when the user or institution `owner` has its own row for this tool (not intersected)."""
    return any(p.action == action for p in owner.permissions)


def stored_tools(owner) -> dict:
    """The tools of a user or institution as saved: {"tracking": bool}."""
    return {name: stored_tool(owner, action) for name, action in TOOLS.items()}


def effective_tools(db: Session, user: User) -> dict:
    """The tools this user has now: {"tracking": bool}.

    General admin: all. No institution: their own. Institution admin: the institution's. Member: their own AND the
    institution's. nginx asks this (through /auth/check) on every request to the tracking service, polling included,
    so it only reads the user's and the institution's rows (relationships already loaded with the user, or one query
    each).
    """
    if user.role == "admin":
        return {name: True for name in TOOLS}
    org = user.organization
    result = {}
    for name, action in TOOLS.items():
        own = stored_tool(user, action)
        if org is None:
            result[name] = own
        elif user.role == "org_admin":
            result[name] = stored_tool(org, action)
        else:
            result[name] = own and stored_tool(org, action)
    return result


def can_use_tool_on(db: Session, user: User, tool: str, radar_code: str) -> bool:
    """A tool on one radar: the tool AND that radar's view. What nginx asks for the per-radar routes of a tool.

    A tracking job costs seconds of CPU, so hiding the button is not enough: the server checks the view too."""
    return effective_tools(db, user)[tool] and radar_code.upper() in effective_radar_views(db, user)


def can_use_tracking_on(db: Session, user: User, radar_code: str) -> bool:
    """can_use_tool_on for the storm tracking tool."""
    return can_use_tool_on(db, user, "tracking", radar_code)


def _set_tools(db: Session, rows: list, tools: dict, granted_by: User) -> None:
    """Put or remove the row of each tool named in `tools` (tools not named are left as they are)."""
    for name, on in tools.items():
        if on is None:
            continue
        _replace_rows(db, rows, {PERMISSION_ALL} if on else set(), granted_by, action=TOOLS[name])


def set_user_tools(db: Session, user: User, tools: dict, granted_by: User, within_company: bool = False) -> dict:
    """Give or take the user's tools and return them as stored.

    within_company=True is the institution admin's case: it can only give a tool its institution has (403); taking one
    away is always allowed. The user row is locked first, like replace_user_radar_views, so two admins saving at once
    do not break the unique constraint."""
    db.refresh(user, with_for_update=True)
    if within_company:
        org = user.organization
        for name, on in tools.items():
            if on and (org is None or not stored_tool(org, TOOLS[name])):
                raise PermissionRuleError(403, "Solo podés asignar herramientas que tenga tu institución")
    _set_tools(db, user.permissions, tools, granted_by)
    return stored_tools(user)


def _give_tool_to_members(db: Session, org: Organization, action: str, granted_by: User) -> None:
    """Give every user of the institution its own row for this tool (those that already have it keep theirs)."""
    members = db.query(User).filter(User.organization_id == org.id).all()
    for member in members:
        if not stored_tool(member, action):
            member.permissions.append(Permission(action=action, resource=PERMISSION_ALL, granted_by=granted_by.id))
    db.flush()


def set_org_tools(db: Session, org: Organization, tools: dict, granted_by: User) -> dict:
    """Give or take an institution's tools.

    Taking one takes it at once from every member (intersection: their own rows stay, but do not count). Giving one
    that the institution did not have gives it to all its users right away; the institution admin can then switch it
    off by hand for whoever should not have it. Saving a tool the institution already has changes nothing, so those
    manual switch-offs are kept."""
    db.refresh(org, with_for_update=True)
    before = stored_tools(org)
    _set_tools(db, org.permissions, tools, granted_by)
    for name, on in tools.items():
        if on and not before[name]:
            _give_tool_to_members(db, org, TOOLS[name], granted_by)
    return stored_tools(org)


def copy_company_tools_to(db: Session, user: User, granted_by: User) -> None:
    """Give an institution member the institution's current tools (a new member starts with what it has)."""
    org = user.organization
    tools = {name: org is not None and stored_tool(org, action) for name, action in TOOLS.items()}
    _set_tools(db, user.permissions, tools, granted_by)


def delete_radar_permissions(db: Session, radar_code: str) -> None:
    """Remove every detail-view permission on a radar that is being deleted (same transaction as the delete).

    Covers the permissions of users and of companies: both name the radar by code."""
    db.query(Permission).filter(Permission.action == RADAR_DETAIL_VIEW, Permission.resource == radar_code).delete(
        synchronize_session=False
    )
