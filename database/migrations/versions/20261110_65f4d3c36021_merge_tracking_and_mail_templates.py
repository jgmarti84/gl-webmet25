"""merge the tracking line and dev's mail templates migration

The tracking line's merge point (54916cffc332: ... + invitations) and dev's
add_mail_templates (f7a8b9c0d1e2) both continue from e6f7a8b9c0d1. This
revision only joins the two heads so `alembic upgrade head` has a single
target; it changes nothing.

Revision ID: 65f4d3c36021
Revises: 54916cffc332, f7a8b9c0d1e2
Create Date: 2026-11-10

"""

# revision identifiers, used by Alembic.
revision = "65f4d3c36021"
down_revision = ("54916cffc332", "f7a8b9c0d1e2")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
