"""Add cog_data_type, cog_cmap, cog_vmin, cog_vmax columns to radar_cogs

Revision ID: 001_add_cog_data_type
Revises: 
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa

revision = '001_add_cog_data_type'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'radar_cogs',
        sa.Column('cog_data_type', sa.String(16), nullable=True,
                  comment='COG data type: raw_float, rgba, or unknown')
    )
    op.add_column(
        'radar_cogs',
        sa.Column('cog_cmap', sa.String(64), nullable=True,
                  comment='Default colormap stored in COG metadata')
    )
    op.add_column(
        'radar_cogs',
        sa.Column('cog_vmin', sa.Float(), nullable=True,
                  comment='Default vmin stored in COG metadata')
    )
    op.add_column(
        'radar_cogs',
        sa.Column('cog_vmax', sa.Float(), nullable=True,
                  comment='Default vmax stored in COG metadata')
    )


def downgrade() -> None:
    op.drop_column('radar_cogs', 'cog_vmax')
    op.drop_column('radar_cogs', 'cog_vmin')
    op.drop_column('radar_cogs', 'cog_cmap')
    op.drop_column('radar_cogs', 'cog_data_type')
