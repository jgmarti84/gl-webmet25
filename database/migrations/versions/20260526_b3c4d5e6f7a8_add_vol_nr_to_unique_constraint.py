"""Add vol_nr to radar_cogs unique constraint and composite index.

Previously the unique constraint on radar_cogs was:
    (radar_code, product_id, observation_time, elevation_angle)

This caused two problems when multiple volumes produce the same field
(e.g. DBZH from vol 01 and DBZH from vol 04 at the same timestamp):

  1. The INSERT for the second volume raised a unique-constraint violation.
  2. The registrar's pre-insert duplicate check saw the first volume's row
     and silently skipped the second — so the file was never indexed.

The fix is to include vol_nr in both the unique constraint and the
composite look-up index, so that rows from different volumes are always
treated as distinct records.

PostgreSQL NULL semantics: two NULL values are NOT considered equal in a
UNIQUE constraint, so legacy rows (vol_nr IS NULL) remain independent —
they are only affected if the rest of the columns are identical.

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f6
Create Date: 2026-05-26
"""

from alembic import op
import sqlalchemy as sa

revision = "b3c4d5e6f7a8"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Drop the old unique constraint (does not include vol_nr).
    op.drop_constraint("uq_cog_radar_product_time_elev", "radar_cogs", type_="unique")

    # 2. Drop the old composite index (will be recreated with vol_nr).
    op.drop_index("idx_cog_radar_product_time", table_name="radar_cogs")

    # 3. Create the new unique constraint that includes vol_nr.
    #    NULLs in vol_nr are treated as distinct by PostgreSQL, which is the
    #    correct behaviour for legacy files that have no vol_nr.
    op.create_unique_constraint(
        "uq_cog_radar_product_time_elev_vol",
        "radar_cogs",
        ["radar_code", "product_id", "observation_time", "elevation_angle", "vol_nr"],
    )

    # 4. Recreate the composite look-up index with vol_nr included.
    op.create_index(
        "idx_cog_radar_product_time",
        "radar_cogs",
        ["radar_code", "product_id", "observation_time", "vol_nr"],
    )


def downgrade() -> None:
    op.drop_index("idx_cog_radar_product_time", table_name="radar_cogs")
    op.drop_constraint("uq_cog_radar_product_time_elev_vol", "radar_cogs", type_="unique")

    op.create_index(
        "idx_cog_radar_product_time",
        "radar_cogs",
        ["radar_code", "product_id", "observation_time"],
    )
    op.create_unique_constraint(
        "uq_cog_radar_product_time_elev",
        "radar_cogs",
        ["radar_code", "product_id", "observation_time", "elevation_angle"],
    )
