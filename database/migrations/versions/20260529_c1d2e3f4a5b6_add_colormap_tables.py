"""Add colormap_stops and product_colormap_options tables; add default_cmap/min_value/max_value to radar_products.

New tables
----------
colormap_stops
    Stores the LinearSegmentedColormap channel breakpoints for every named
    colormap (system-defined or user-defined).  Each row is one (position,
    val_left, val_right) triple for a single channel (r/g/b) of a named
    colormap.  sort_order keeps rows stable when a position appears twice
    (colour discontinuity).

product_colormap_options
    Explicit list of colormaps available in the UI dropdown for each
    product_key.  When a product has no rows here the frontend falls back
    to showing all colormaps in colormap_stops.

Column additions to radar_products
-----------------------------------
default_cmap  — name of the default colormap for the product.
min_value     — already existed as nullable Float; no DDL change needed.
max_value     — already existed as nullable Float; no DDL change needed.

Revision ID: c1d2e3f4a5b6
Revises: b3c4d5e6f7a8
Create Date: 2026-05-29
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect, text

revision = "c1d2e3f4a5b6"
down_revision = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    # ── 1. default_cmap column on radar_products (idempotent) ───────────────
    existing_cols = [c["name"] for c in inspector.get_columns("radar_products")]
    if "default_cmap" not in existing_cols:
        op.add_column(
            "radar_products",
            sa.Column(
                "default_cmap",
                sa.String(64),
                nullable=True,
                comment="Default colormap name for this product",
            ),
        )

    # ── 2. colormap_stops (idempotent) ──────────────────────────────────────
    if not inspector.has_table("colormap_stops"):
        op.create_table(
            "colormap_stops",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "cmap_name",
                sa.String(64),
                nullable=False,
                comment="Colormap identifier, e.g. grc_th, grc_vrad",
            ),
            sa.Column(
                "channel",
                sa.String(1),
                nullable=False,
                comment="Colour channel: r, g or b",
            ),
            sa.Column(
                "position",
                sa.Float(),
                nullable=False,
                comment="Normalised position in [0, 1]",
            ),
            sa.Column(
                "val_left",
                sa.Float(),
                nullable=False,
                comment="Channel value approaching this position from the left (y0)",
            ),
            sa.Column(
                "val_right",
                sa.Float(),
                nullable=False,
                comment="Channel value leaving this position to the right (y1); equals val_left for continuous points",
            ),
            sa.Column(
                "sort_order",
                sa.Integer(),
                nullable=False,
                server_default="0",
                comment="Stable ordering within (cmap_name, channel); required when position repeats",
            ),
            sa.Column(
                "is_system",
                sa.Boolean(),
                nullable=False,
                server_default="true",
                comment="System colormaps cannot be deleted via the API",
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "idx_cmap_stop_name_channel_order",
            "colormap_stops",
            ["cmap_name", "channel", "sort_order"],
        )

    # ── 3. product_colormap_options (idempotent) ────────────────────────────
    if not inspector.has_table("product_colormap_options"):
        op.create_table(
            "product_colormap_options",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "product_key",
                sa.String(16),
                sa.ForeignKey("radar_products.product_key", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "cmap_name",
                sa.String(64),
                nullable=False,
                comment="Colormap name; must match ColormapStop.cmap_name",
            ),
            sa.UniqueConstraint(
                "product_key",
                "cmap_name",
                name="uq_product_colormap_option",
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    if inspector.has_table("product_colormap_options"):
        op.drop_table("product_colormap_options")

    if inspector.has_table("colormap_stops"):
        # drop_index with if_exists so it's safe even if the index is missing
        op.drop_index(
            "idx_cmap_stop_name_channel_order",
            table_name="colormap_stops",
            if_exists=True,
        )
        op.drop_table("colormap_stops")

    existing_cols = [c["name"] for c in inspector.get_columns("radar_products")]
    if "default_cmap" in existing_cols:
        op.drop_column("radar_products", "default_cmap")
