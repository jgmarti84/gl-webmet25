"""Add vol_nr and radar_coverage_m columns to radar_cogs table.

Revision ID: a1b2c3d4e5f6
Revises: 3a7f2c91d4e8
Create Date: 2026-05-18
"""

from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "3a7f2c91d4e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add vol_nr and radar_coverage_m columns."""
    op.add_column(
        "radar_cogs",
        sa.Column("vol_nr", sa.String(16), nullable=True),
    )
    op.create_index("ix_radar_cogs_vol_nr", "radar_cogs", ["vol_nr"])

    op.add_column(
        "radar_cogs",
        sa.Column("radar_coverage_m", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    """Remove vol_nr and radar_coverage_m columns."""
    op.drop_index("ix_radar_cogs_vol_nr", table_name="radar_cogs")
    op.drop_column("radar_cogs", "radar_coverage_m")
    op.drop_column("radar_cogs", "vol_nr")
