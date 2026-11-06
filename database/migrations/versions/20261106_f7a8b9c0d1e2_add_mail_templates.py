"""Editable mail texts (spec F): the mail_templates table.

Every step checks first, so it also works on a database that create_all() already built with the new model.

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-11-06
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"  # add_invitations (spec E)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create mail_templates: one row per mail that was customized (no rows = every mail uses its default text)."""
    if "mail_templates" in inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "mail_templates",
        sa.Column("key", sa.String(32), primary_key=True),
        sa.Column("subject", sa.String(150), nullable=False),
        sa.Column("heading", sa.String(120), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("button", sa.String(40), nullable=False),
        sa.Column("footer", sa.String(400), nullable=False),
        sa.Column("fallback", sa.String(200), nullable=False),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "key IN ('verify_email', 'reset_password', 'account_exists', 'invitation')", name="ck_mail_templates_key"
        ),
        sa.CheckConstraint("char_length(subject) BETWEEN 1 AND 150", name="ck_mail_templates_subject_len"),
        sa.CheckConstraint("char_length(heading) BETWEEN 1 AND 120", name="ck_mail_templates_heading_len"),
        sa.CheckConstraint("char_length(body) BETWEEN 1 AND 2000", name="ck_mail_templates_body_len"),
        sa.CheckConstraint("char_length(button) BETWEEN 1 AND 40", name="ck_mail_templates_button_len"),
        sa.CheckConstraint("char_length(footer) BETWEEN 1 AND 400", name="ck_mail_templates_footer_len"),
        sa.CheckConstraint("char_length(fallback) BETWEEN 1 AND 200", name="ck_mail_templates_fallback_len"),
    )


def downgrade() -> None:
    """Drop the table: the customized texts are lost and every mail goes back to its default text."""
    op.drop_table("mail_templates")
