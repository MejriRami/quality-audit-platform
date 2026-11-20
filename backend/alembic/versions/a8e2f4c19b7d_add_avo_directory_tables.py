"""add avo directory tables: local mirror of the Northwind Central MCP
people directory, plus a sync-status singleton row, plus an optional
people_id link on audit_auditees

Revision ID: a8e2f4c19b7d
Revises: e7a1b4c9f3d2
Create Date: 2026-08-13 00:00:00.000000

Additive-only: two new tables, and one new nullable FK column on the
existing audit_auditees table. Nothing here touches existing rows -
audit_auditees.email stays the source of truth, people_id starts NULL for
every existing row and is only populated going forward when an auditee is
picked from the directory instead of typed manually.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8e2f4c19b7d"
down_revision: Union[str, Sequence[str], None] = "e7a1b4c9f3d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "org_directory_members",
        sa.Column("people_id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=150), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("work_unit_name", sa.String(length=150), nullable=True),
        sa.Column("role_name", sa.String(length=150), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("last_synced_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_avo_directory_members_email", "org_directory_members", ["email"]
    )
    op.create_index(
        "ix_avo_directory_members_email", "org_directory_members", ["email"]
    )

    op.create_table(
        "org_directory_sync_status",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("last_attempt_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("alerted_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    # Seed the one singleton row the sync job expects to always find.
    op.execute(
        "INSERT INTO org_directory_sync_status (id, consecutive_failures) "
        "VALUES (1, 0)"
    )

    op.add_column(
        "audit_auditees",
        sa.Column("people_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_audit_auditees_people_id",
        "audit_auditees",
        "org_directory_members",
        ["people_id"],
        ["people_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_audit_auditees_people_id", "audit_auditees", type_="foreignkey"
    )
    op.drop_column("audit_auditees", "people_id")
    op.drop_table("org_directory_sync_status")
    op.drop_index("ix_avo_directory_members_email", table_name="org_directory_members")
    op.drop_constraint(
        "uq_avo_directory_members_email", "org_directory_members", type_="unique"
    )
    op.drop_table("org_directory_members")
