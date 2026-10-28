"""One user_sessions row per login, rotated in place.

Each family of refresh rows becomes its login row (the oldest one): refresh_count and last_used_at summarize
the family, and logins that were still open are closed (revoke_reason 'migration'), because the refresh token
format changes and every user logs in again once.

Revision ID: a8b9c0d1e2f3
Revises: e7f8a9b0c1d2
Create Date: 2026-10-27
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "a8b9c0d1e2f3"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None

# The oldest row of each family is the login itself (created_at, then id to break ties).
# DISTINCT ON keeps the first row of each family_id in the ORDER BY order.
FIRST_ROWS = "SELECT DISTINCT ON (family_id) id, family_id FROM user_sessions ORDER BY family_id, created_at, id"

# Summarize every family into its login row. A login counts as still open when any of its rows has no
# revoked_at (the oldest row is almost always revoked by the first rotation, so it cannot decide alone).
COMPACT = f"""
WITH family AS (
    SELECT family_id,
           count(*) AS rows,
           max(last_used_at) AS last_used,
           bool_or(revoked_at IS NULL) AS still_open,
           max(revoked_at) AS last_revoked
    FROM user_sessions
    GROUP BY family_id
), first_row AS ({FIRST_ROWS})
UPDATE user_sessions AS s SET
    refresh_count = family.rows - 1,
    last_used_at = family.last_used,
    revoked_at = CASE WHEN family.still_open THEN now() ELSE family.last_revoked END,
    revoke_reason = CASE WHEN family.still_open THEN 'migration' ELSE NULL END
FROM first_row JOIN family USING (family_id)
WHERE s.id = first_row.id
"""

# Every other row of a family was one refresh: the login row already summarizes it.
DELETE_REFRESH_ROWS = f"DELETE FROM user_sessions WHERE id NOT IN (SELECT id FROM ({FIRST_ROWS}) AS first_row)"


def _columns() -> set:
    """Column names of user_sessions as the database has them right now."""
    return {c["name"] for c in inspect(op.get_bind()).get_columns("user_sessions")}


def upgrade() -> None:
    """Add the new columns, compact each family to its login row and drop the family columns."""
    if "family_id" not in _columns():
        return  # already one row per login (database created by create_all from the new models)

    op.add_column("user_sessions", sa.Column("previous_token_hash", sa.String(64)))
    op.add_column("user_sessions", sa.Column("rotated_at", sa.DateTime(timezone=True)))
    op.add_column("user_sessions", sa.Column("refresh_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("user_sessions", sa.Column("revoke_reason", sa.String(20)))

    op.execute(COMPACT)
    op.execute(DELETE_REFRESH_ROWS)

    op.drop_index("ix_user_sessions_family_id", table_name="user_sessions")
    op.drop_column("user_sessions", "replaced_by")
    op.drop_column("user_sessions", "family_id")


def downgrade() -> None:
    """Bring back family_id (one family per login row) and replaced_by; the compacted refresh rows stay gone."""
    op.add_column("user_sessions", sa.Column("family_id", postgresql.UUID(as_uuid=True)))
    op.add_column("user_sessions", sa.Column("replaced_by", postgresql.UUID(as_uuid=True)))
    op.execute("UPDATE user_sessions SET family_id = id")
    op.alter_column("user_sessions", "family_id", nullable=False)
    op.create_index("ix_user_sessions_family_id", "user_sessions", ["family_id"])

    op.drop_column("user_sessions", "revoke_reason")
    op.drop_column("user_sessions", "refresh_count")
    op.drop_column("user_sessions", "rotated_at")
    op.drop_column("user_sessions", "previous_token_hash")
