"""merge the nccubes (tracking) and users/sessions (login) migration branches

Both branches were started from d4e5f6a7b8c9: the tracking work added the
nccubes table (e5f6a7b8c9d0) and the login work added users, sessions and
e-mail tokens (e7f8a9b0c1d2 ... b2c3d4e5f6a7). This revision only joins the
two heads so `alembic upgrade head` has a single target; it changes nothing.

A database at either branch (or before both) upgrades cleanly: Alembic
applies whichever side is missing, then this merge point.

Revision ID: 17416fd2d8aa
Revises: e5f6a7b8c9d0, b2c3d4e5f6a7
Create Date: 2026-10-28

"""

# revision identifiers, used by Alembic.
revision = "17416fd2d8aa"
down_revision = ("e5f6a7b8c9d0", "b2c3d4e5f6a7")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
