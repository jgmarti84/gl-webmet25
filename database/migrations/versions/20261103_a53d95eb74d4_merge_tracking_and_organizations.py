"""merge the tracking line and dev's organizations migration

The tracking line's merge point (d421ffd04273: nccubes + users + permissions) and
dev's add_organizations (d5e6f7a8b9c0) both continue from c4d5e6f7a8b9. This
revision only joins the two heads so `alembic upgrade head` has a single target;
it changes nothing.

Stage databases that ran the tracking merge before it was renumbered are stamped
d5e6f7a8b9c0, which now means add_organizations. Fix them once, before upgrading:

    alembic stamp --purge d421ffd04273
    alembic upgrade head

Revision ID: a53d95eb74d4
Revises: d421ffd04273, d5e6f7a8b9c0
Create Date: 2026-11-03

"""

# revision identifiers, used by Alembic.
revision = "a53d95eb74d4"
down_revision = ("d421ffd04273", "d5e6f7a8b9c0")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
