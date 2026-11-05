"""merge the tracking line and dev's invitations migration

The tracking line's merge point (a53d95eb74d4: nccubes + users + permissions +
organizations) and dev's add_invitations (e6f7a8b9c0d1) both continue from
d5e6f7a8b9c0. This revision only joins the two heads so `alembic upgrade head`
has a single target; it changes nothing.

Revision ID: 54916cffc332
Revises: a53d95eb74d4, e6f7a8b9c0d1
Create Date: 2026-11-05

"""

# revision identifiers, used by Alembic.
revision = "54916cffc332"
down_revision = ("a53d95eb74d4", "e6f7a8b9c0d1")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
