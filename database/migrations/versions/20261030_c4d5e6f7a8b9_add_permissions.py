"""Add the permissions table (spec C, plan C-1): which one-radar detail views each user may open.

Existing users get no rows (decision C15): after this migration only admins see detail views until an admin
assigns them.

Revision ID: c4d5e6f7a8b9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "c4d5e6f7a8b9"
down_revision = "c3d4e5f6a7b8"  # add_google_sub_to_users (login with Google)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the table, unless the database came from create_all() with the new models (it already has it)."""
    if "permissions" in inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource", sa.String(64), nullable=False),
        sa.Column("granted_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("action IN ('radar.detail_view')", name="ck_permissions_action"),
        sa.UniqueConstraint("user_id", "action", "resource", name="uq_permissions_user_action_resource"),
    )


def downgrade() -> None:
    op.drop_table("permissions")
