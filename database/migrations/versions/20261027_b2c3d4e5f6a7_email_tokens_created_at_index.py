"""Index email_tokens by created_at, for the global sending caps.

The global caps count the mails of the whole site in the last hour and the last day on every mail that may go out.
The existing index (user_id, created_at) cannot serve a filter without user_id, so without this one each count would
read the whole table.

Revision ID: b2c3d4e5f6a7
Revises: f1a2b3c4d5e6
Create Date: 2026-10-27
"""

from alembic import op
from sqlalchemy import inspect

revision = "b2c3d4e5f6a7"
down_revision = "f1a2b3c4d5e6"  # add_email_verification (spec B)
branch_labels = None
depends_on = None

INDEX = "ix_email_tokens_created_at"


def upgrade() -> None:
    """Create the index, unless the database came from create_all() with the new models (it already has it)."""
    if INDEX not in {i["name"] for i in inspect(op.get_bind()).get_indexes("email_tokens")}:
        op.create_index(INDEX, "email_tokens", ["created_at"])


def downgrade() -> None:
    op.drop_index(INDEX, table_name="email_tokens")
