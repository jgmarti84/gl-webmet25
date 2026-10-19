"""Add users and user_sessions tables.

users          application accounts (admin / viewer)
user_sessions  one row per refresh token, rotated on every refresh

Revision ID: e7f8a9b0c1d2
Revises: d4e5f6a7b8c9
Create Date: 2026-10-19
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "e7f8a9b0c1d2"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    tables = inspect(conn).get_table_names()

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("username", sa.String(32), nullable=False),
            sa.Column("full_name", sa.String(128)),
            sa.Column("email", sa.String(254)),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.Column("role", sa.String(16), nullable=False, server_default="viewer"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("password_is_bootstrap", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("locked_until", sa.DateTime(timezone=True)),
            sa.Column("last_login_at", sa.DateTime(timezone=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
            sa.CheckConstraint("role IN ('admin', 'viewer')", name="ck_users_role"),
        )
        op.create_index("ix_users_username", "users", ["username"], unique=True)

    if "user_sessions" not in tables:
        op.create_table(
            "user_sessions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("absolute_expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True)),
            sa.Column("replaced_by", postgresql.UUID(as_uuid=True)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("last_used_at", sa.DateTime(timezone=True)),
            sa.Column("user_agent", sa.String(256)),
            sa.Column("ip", sa.String(45)),
        )
        op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
        op.create_index("ix_user_sessions_family_id", "user_sessions", ["family_id"])


def downgrade() -> None:
    op.drop_table("user_sessions")
    op.drop_table("users")
