"""add unavailability approval workflow columns

Revision ID: f1c2b3a4d5e6
Revises: 559b014d02d0
Create Date: 2026-04-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f1c2b3a4d5e6"
down_revision: Union[str, Sequence[str], None] = "559b014d02d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "audit_unavailability",
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="approved",
        ),
    )
    op.add_column(
        "audit_unavailability",
        sa.Column("requested_by_email", sa.String(length=150), nullable=True),
    )
    op.add_column(
        "audit_unavailability",
        sa.Column("plant_manager_email", sa.String(length=150), nullable=True),
    )
    op.add_column(
        "audit_unavailability",
        sa.Column("decision_by_email", sa.String(length=150), nullable=True),
    )
    op.add_column(
        "audit_unavailability",
        sa.Column("decision_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "audit_unavailability",
        sa.Column("decision_comment", sa.String(length=255), nullable=True),
    )
    op.alter_column("audit_unavailability", "status", server_default=None)


def downgrade() -> None:
    op.drop_column("audit_unavailability", "decision_comment")
    op.drop_column("audit_unavailability", "decision_at")
    op.drop_column("audit_unavailability", "decision_by_email")
    op.drop_column("audit_unavailability", "plant_manager_email")
    op.drop_column("audit_unavailability", "requested_by_email")
    op.drop_column("audit_unavailability", "status")
