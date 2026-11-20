"""add auditee portal email otps

Revision ID: a7b3c2d1e4f5
Revises: fd3261252793
Create Date: 2026-05-19 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a7b3c2d1e4f5"
down_revision: Union[str, Sequence[str], None] = "fd3261252793"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auditee_portal_email_otps",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plant", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=150), nullable=False),
        sa.Column("code", sa.String(length=6), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_auditee_portal_email_otps_plant",
        "auditee_portal_email_otps",
        ["plant"],
        unique=False,
    )
    op.create_index(
        "ix_auditee_portal_email_otps_email",
        "auditee_portal_email_otps",
        ["email"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_auditee_portal_email_otps_email", table_name="auditee_portal_email_otps")
    op.drop_index("ix_auditee_portal_email_otps_plant", table_name="auditee_portal_email_otps")
    op.drop_table("auditee_portal_email_otps")
