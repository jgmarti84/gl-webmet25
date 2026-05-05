"""add tops_and_cores table

Revision ID: 3a7f2c91d4e8
Revises: 
Create Date: 2026-05-05

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '3a7f2c91d4e8'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'tops_and_cores',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('radar_code', sa.String(length=16), nullable=False),
        sa.Column('observation_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('file_path', sa.String(length=512), nullable=False),
        sa.Column('file_name', sa.String(length=256), nullable=False),
        sa.Column('feature_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('core_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('top_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column(
            'status',
            sa.Enum(
                'pending', 'available', 'processing', 'error', 'archived', 'missing',
                name='cogstatus',
                create_type=False,
            ),
            nullable=False,
            server_default='available',
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
        sa.UniqueConstraint('file_path', name='uq_tops_and_cores_file_path'),
    )
    op.create_index(
        'idx_tops_and_cores_observation_time',
        'tops_and_cores',
        ['observation_time'],
    )
    op.create_index(
        'idx_tops_and_cores_radar_code',
        'tops_and_cores',
        ['radar_code'],
    )
    op.create_index(
        'idx_tops_and_cores_status',
        'tops_and_cores',
        ['status'],
    )


def downgrade() -> None:
    op.drop_index('idx_tops_and_cores_status', table_name='tops_and_cores')
    op.drop_index('idx_tops_and_cores_radar_code', table_name='tops_and_cores')
    op.drop_index('idx_tops_and_cores_observation_time', table_name='tops_and_cores')
    op.drop_table('tops_and_cores')
