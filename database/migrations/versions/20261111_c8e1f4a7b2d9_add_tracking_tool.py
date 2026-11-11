"""Storm tracking tool: allow the "tool.tracking" permission and let invitations carry the choice.

Every step checks first, so it also works on a database that create_all() already built with the new models.
After this migration nobody has the tool (there are no rows): the general admin grants it.

Revision ID: c8e1f4a7b2d9
Revises: 65f4d3c36021
Create Date: 2026-11-11
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "c8e1f4a7b2d9"
down_revision = "65f4d3c36021"  # merge of the tracking and mail templates heads
branch_labels = None
depends_on = None

OLD_ACTIONS = "action IN ('radar.detail_view')"
NEW_ACTIONS = "action IN ('radar.detail_view', 'tool.tracking')"


def _checks(table: str) -> dict:
    """Check constraints of a table as {name: sql text}."""
    return {c["name"]: c["sqltext"] for c in inspect(op.get_bind()).get_check_constraints(table)}


def upgrade() -> None:
    """Widen the allowed actions and add invitations.tracking with its rule."""
    if "tool.tracking" not in str(_checks("permissions").get("ck_permissions_action", "")):
        op.drop_constraint("ck_permissions_action", "permissions", type_="check")
        op.create_check_constraint("ck_permissions_action", "permissions", NEW_ACTIONS)
    if "tracking" not in {c["name"] for c in inspect(op.get_bind()).get_columns("invitations")}:
        op.add_column("invitations", sa.Column("tracking", sa.Boolean(), nullable=True))
    if "ck_invitations_tracking_only_viewer" not in _checks("invitations"):
        op.create_check_constraint(
            "ck_invitations_tracking_only_viewer", "invitations", "role = 'viewer' OR tracking IS NULL"
        )


def downgrade() -> None:
    """Remove the tool everywhere and go back to radar views only."""
    op.execute("DELETE FROM permissions WHERE action = 'tool.tracking'")
    op.drop_constraint("ck_invitations_tracking_only_viewer", "invitations", type_="check")
    op.drop_column("invitations", "tracking")
    op.drop_constraint("ck_permissions_action", "permissions", type_="check")
    op.create_check_constraint("ck_permissions_action", "permissions", OLD_ACTIONS)
