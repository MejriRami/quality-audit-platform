"""add portal access sessions and otp modes

Revision ID: b4c5d6e7f8a9
Revises: a7b3c2d1e4f5
Create Date: 2026-05-19 15:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, Sequence[str], None] = "a7b3c2d1e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "auditee_portal_email_otps",
        sa.Column("access_mode", sa.String(length=20), nullable=True, server_default="auditee"),
    )
    op.create_index(
        "ix_auditee_portal_email_otps_access_mode",
        "auditee_portal_email_otps",
        ["access_mode"],
        unique=False,
    )
    op.alter_column("auditee_portal_email_otps", "access_mode", nullable=False, server_default=None)

    op.create_table(
        "portal_access_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plant", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=150), nullable=False),
        sa.Column("access_mode", sa.String(length=20), nullable=False),
        sa.Column("session_token", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_token"),
    )
    op.create_index("ix_portal_access_sessions_plant", "portal_access_sessions", ["plant"], unique=False)
    op.create_index("ix_portal_access_sessions_email", "portal_access_sessions", ["email"], unique=False)
    op.create_index("ix_portal_access_sessions_access_mode", "portal_access_sessions", ["access_mode"], unique=False)
    op.create_index("ix_portal_access_sessions_session_token", "portal_access_sessions", ["session_token"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_portal_access_sessions_session_token", table_name="portal_access_sessions")
    op.drop_index("ix_portal_access_sessions_access_mode", table_name="portal_access_sessions")
    op.drop_index("ix_portal_access_sessions_email", table_name="portal_access_sessions")
    op.drop_index("ix_portal_access_sessions_plant", table_name="portal_access_sessions")
    op.drop_table("portal_access_sessions")

    op.drop_index("ix_auditee_portal_email_otps_access_mode", table_name="auditee_portal_email_otps")
    op.drop_column("auditee_portal_email_otps", "access_mode")
