"""add nccubes table

Indexes the 3D Cartesian radar volumes ("NC cubes") written by radarlib's
product daemon. These are the input to on-demand storm tracking.

Note the PgEnum import: `sa.Enum(..., create_type=False)` does not reliably
suppress CREATE TYPE inside op.create_table, so referencing the existing shared
`cogstatus` type must go through the postgresql dialect ENUM instead.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-20

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM as PgEnum

# revision identifiers, used by Alembic.
revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'nccubes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('radar_code', sa.String(length=16), nullable=False),
        sa.Column('observation_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('file_path', sa.String(length=512), nullable=False),
        sa.Column('file_name', sa.String(length=256), nullable=False),
        sa.Column('file_size_bytes', sa.Integer(), nullable=True),
        sa.Column('file_mtime', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'status',
            PgEnum(
                'PENDING', 'AVAILABLE', 'PROCESSING', 'ERROR', 'ARCHIVED', 'MISSING',
                name='cogstatus',
                create_type=False,
            ),
            nullable=False,
            server_default='AVAILABLE',
        ),
        sa.Column('strategy', sa.String(length=32), nullable=True),
        sa.Column('vol_nr', sa.String(length=16), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
        ),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ['radar_code'],
            ['radars.code'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('file_path', name='uq_nccubes_file_path'),
    )
    op.create_index(
        'idx_nccubes_observation_time',
        'nccubes',
        ['observation_time'],
    )
    op.create_index(
        'idx_nccubes_radar_code',
        'nccubes',
        ['radar_code'],
    )
    op.create_index(
        'idx_nccubes_status',
        'nccubes',
        ['status'],
    )
    # The sidecar's only query shape: one radar, one time window, ordered.
    op.create_index(
        'idx_nccube_radar_time',
        'nccubes',
        ['radar_code', 'observation_time'],
    )


def downgrade() -> None:
    op.drop_index('idx_nccube_radar_time', table_name='nccubes')
    op.drop_index('idx_nccubes_status', table_name='nccubes')
    op.drop_index('idx_nccubes_radar_code', table_name='nccubes')
    op.drop_index('idx_nccubes_observation_time', table_name='nccubes')
    op.drop_table('nccubes')
