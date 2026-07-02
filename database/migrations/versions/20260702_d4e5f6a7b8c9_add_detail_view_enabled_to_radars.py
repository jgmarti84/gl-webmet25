"""Add detail_view_enabled to radars table.

Column
------
detail_view_enabled (Boolean, NOT NULL, DEFAULT FALSE)
    Controls whether the one-radar detail view (radar.html) is accessible
    for this radar station.  Set to TRUE for RMA1 via a data migration so
    it is always enabled out of the box.

Revision ID: d4e5f6a7b8c9
Revises: c1d2e3f4a5b6
Create Date: 2026-07-02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "d4e5f6a7b8c9"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    # ── 1. Add detail_view_enabled column (idempotent) ───────────────────────
    existing_cols = [c["name"] for c in inspector.get_columns("radars")]
    if "detail_view_enabled" not in existing_cols:
        op.add_column(
            "radars",
            sa.Column(
                "detail_view_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )

    # ── 2. Data migration: enable detail view for RMA1 ───────────────────────
    conn.execute(
        text("UPDATE radars SET detail_view_enabled = TRUE WHERE code = 'RMA1'")
    )


def downgrade() -> None:
    op.drop_column("radars", "detail_view_enabled")
