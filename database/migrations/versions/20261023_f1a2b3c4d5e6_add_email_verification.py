"""Add e-mail verification: users.email_verified_at / terms_accepted_at, unique e-mail, email_tokens.

Existing accounts were created by an admin, so they are marked as verified.

Revision ID: f1a2b3c4d5e6
Revises: a8b9c0d1e2f3
Create Date: 2026-10-23
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "f1a2b3c4d5e6"
down_revision = "a8b9c0d1e2f3"  # one_session_row_per_login (sessions spec)
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = inspect(conn)

    # Every step is guarded: the database may come from create_all() with the new models already in place.
    columns = {c["name"] for c in insp.get_columns("users")}
    if "email_verified_at" not in columns:
        op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True)))
        # Only on the first run: accounts that exist today were created by an admin, nobody asked them to verify.
        op.execute("UPDATE users SET email_verified_at = now() WHERE email_verified_at IS NULL")
    if "terms_accepted_at" not in columns:
        op.add_column("users", sa.Column("terms_accepted_at", sa.DateTime(timezone=True)))

    # Normalize first, then look for duplicates: two mails that only differ in case must be caught.
    op.execute("UPDATE users SET email = NULLIF(lower(btrim(email)), '') WHERE email IS NOT NULL")
    duplicates = conn.execute(
        sa.text("SELECT email, count(*) FROM users WHERE email IS NOT NULL GROUP BY email HAVING count(*) > 1")
    ).fetchall()
    if duplicates:
        # Fail loudly instead of picking a winner: only a person can decide which account keeps the mail.
        listed = ", ".join(f"{row[0]} ({row[1]})" for row in duplicates)
        raise RuntimeError(
            f"Hay mails repetidos en la tabla users: {listed}. Corregilos (cambiá o borrá el mail de las "
            "cuentas repetidas) y volvé a correr la migración."
        )

    indexes = {i["name"] for i in insp.get_indexes("users")}
    if "uq_users_email" not in indexes:
        op.create_index(
            "uq_users_email", "users", ["email"], unique=True, postgresql_where=sa.text("email IS NOT NULL")
        )

    if "email_tokens" not in insp.get_table_names():
        op.create_table(
            "email_tokens",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("purpose", sa.String(32), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True)),
            sa.CheckConstraint(
                "purpose IN ('verify_email', 'reset_password', 'account_exists')", name="ck_email_tokens_purpose"
            ),
        )
        op.create_index("ix_email_tokens_user_created", "email_tokens", ["user_id", "created_at"])


def downgrade() -> None:
    # People who registered keep their user but lose the "verified" mark.
    op.drop_table("email_tokens")
    op.drop_index("uq_users_email", table_name="users")
    op.drop_column("users", "terms_accepted_at")
    op.drop_column("users", "email_verified_at")
