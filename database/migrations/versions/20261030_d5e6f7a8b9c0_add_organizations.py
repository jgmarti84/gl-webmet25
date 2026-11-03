"""Company accounts (spec C, plan C-2): organizations, users.organization_id, the org_admin role, and
company-owned permissions.

Every step checks first, so it also works on a database that create_all() already built with the new models.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-10-30
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"  # add_permissions (plan C-1)
branch_labels = None
depends_on = None


def _checks(table: str) -> set:
    return {c["name"] for c in inspect(op.get_bind()).get_check_constraints(table)}


def _columns(table: str) -> set:
    return {c["name"] for c in inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    """Create organizations, link users and permissions to them, and allow the org_admin role."""
    if "organizations" not in inspect(op.get_bind()).get_table_names():
        op.create_table(
            "organizations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("name", sa.String(128), nullable=False, unique=True),
            sa.Column("seat_limit", sa.Integer(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True)),
            sa.CheckConstraint("seat_limit > 0", name="ck_organizations_seat_limit"),
        )

    if "organization_id" not in _columns("users"):
        op.add_column("users", sa.Column("organization_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_users_organization_id", "users", "organizations", ["organization_id"], ["id"], ondelete="RESTRICT"
        )
        op.create_index("ix_users_organization_id", "users", ["organization_id"])

    # Replace the role check (it only allowed admin and viewer) and add the two company rules.
    if "ck_users_org_admin_has_org" not in _checks("users"):
        op.drop_constraint("ck_users_role", "users", type_="check")
        op.create_check_constraint("ck_users_role", "users", "role IN ('admin', 'org_admin', 'viewer')")
        op.create_check_constraint(
            "ck_users_org_admin_has_org", "users", "role <> 'org_admin' OR organization_id IS NOT NULL"
        )
        op.create_check_constraint("ck_users_admin_has_no_org", "users", "role <> 'admin' OR organization_id IS NULL")

    if "organization_id" not in _columns("permissions"):
        op.alter_column("permissions", "user_id", existing_type=sa.Integer(), nullable=True)
        op.add_column("permissions", sa.Column("organization_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            "fk_permissions_organization_id",
            "permissions",
            "organizations",
            ["organization_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_check_constraint(
            "ck_permissions_one_subject", "permissions", "(user_id IS NULL) <> (organization_id IS NULL)"
        )
        op.create_unique_constraint(
            "uq_permissions_org_action_resource", "permissions", ["organization_id", "action", "resource"]
        )


def downgrade() -> None:
    """Undo it, but only when no company data would be lost."""
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT count(*) FROM users WHERE organization_id IS NOT NULL")).scalar():
        raise RuntimeError("There are users in companies: move or delete them before downgrading")
    if bind.execute(sa.text("SELECT count(*) FROM permissions WHERE organization_id IS NOT NULL")).scalar():
        raise RuntimeError("There are company permissions: delete them before downgrading")
    op.drop_constraint("uq_permissions_org_action_resource", "permissions", type_="unique")
    op.drop_constraint("ck_permissions_one_subject", "permissions", type_="check")
    op.drop_constraint("fk_permissions_organization_id", "permissions", type_="foreignkey")
    op.drop_column("permissions", "organization_id")
    op.alter_column("permissions", "user_id", existing_type=sa.Integer(), nullable=False)
    op.drop_constraint("ck_users_admin_has_no_org", "users", type_="check")
    op.drop_constraint("ck_users_org_admin_has_org", "users", type_="check")
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.create_check_constraint("ck_users_role", "users", "role IN ('admin', 'viewer')")
    op.drop_index("ix_users_organization_id", table_name="users")
    op.drop_constraint("fk_users_organization_id", "users", type_="foreignkey")
    op.drop_column("users", "organization_id")
    op.drop_table("organizations")
