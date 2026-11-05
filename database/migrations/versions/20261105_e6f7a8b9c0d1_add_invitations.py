"""Invitations by mail (spec E): the invitations table.

Every step checks first, so it also works on a database that create_all() already built with the new model.

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"  # add_organizations (spec C)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create invitations: who was invited to which organization, with which role, and the state of the link."""
    if "invitations" in inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("radar_views", sa.JSON(), nullable=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("invited_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invited_by"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint("role IN ('org_admin', 'viewer')", name="ck_invitations_role"),
        sa.CheckConstraint("role = 'viewer' OR radar_views IS NULL", name="ck_invitations_views_only_viewer"),
    )
    op.create_index("ix_invitations_email", "invitations", ["email"])
    op.create_index("ix_invitations_organization_id", "invitations", ["organization_id"])
    op.create_index("ix_invitations_created_at", "invitations", ["created_at"])


def downgrade() -> None:
    """Drop the invitations table (the invitations themselves are lost; no account depends on them)."""
    op.drop_table("invitations")
