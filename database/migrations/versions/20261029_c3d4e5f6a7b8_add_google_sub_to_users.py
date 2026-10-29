"""Add users.google_sub: the fixed identifier of the Google account linked to a user.

The mail of a Google account can change or be reused, so once a user signs in with Google the "sub" (a number that
never changes for that Google account) is stored and used from then on. Unique among the users that have one.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"  # email_tokens_created_at_index
branch_labels = None
depends_on = None

INDEX = "uq_users_google_sub"


def upgrade() -> None:
    """Every step is guarded: the database may come from create_all() with the new model already in place."""
    insp = inspect(op.get_bind())
    if "google_sub" not in {c["name"] for c in insp.get_columns("users")}:
        op.add_column("users", sa.Column("google_sub", sa.String(255)))
    if INDEX not in {i["name"] for i in insp.get_indexes("users")}:
        op.create_index(INDEX, "users", ["google_sub"], unique=True, postgresql_where=sa.text("google_sub IS NOT NULL"))


def downgrade() -> None:
    op.drop_index(INDEX, table_name="users")
    op.drop_column("users", "google_sub")
