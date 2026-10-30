"""merge the tracking (nccubes + users) and permissions (Google sign-in) migration branches

Both branches continue from b2c3d4e5f6a7: the tracking line joined nccubes and the
login tables (17416fd2d8aa), and dev added google_sub on users (c3d4e5f6a7b8) and
the permissions table (c4d5e6f7a8b9). This revision only joins the two heads so
`alembic upgrade head` has a single target; it changes nothing.

A database at either branch upgrades cleanly: Alembic applies whichever side is
missing, then this merge point.

Revision ID: d5e6f7a8b9c0
Revises: 17416fd2d8aa, c4d5e6f7a8b9
Create Date: 2026-10-30

"""

# revision identifiers, used by Alembic.
revision = "d5e6f7a8b9c0"
down_revision = ("17416fd2d8aa", "c4d5e6f7a8b9")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
