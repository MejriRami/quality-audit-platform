"""Add identifier to car and audit answer

Revision ID: 6da5315c52bf
Revises: c31a7d07dc5c
Create Date: 2026-01-15 11:16:50.085421

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6da5315c52bf'
down_revision: Union[str, Sequence[str], None] = 'c31a7d07dc5c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Add identifier column (nullable by default)
    op.add_column(
        "corrective_actions",
        sa.Column("identifier", sa.String(length=20), nullable=True)
    )

    op.add_column(
        "audit_answers",
        sa.Column("identifier", sa.String(length=20), nullable=True)
    )

    # Add unique constraints
    op.create_unique_constraint(
        "uq_corrective_actions_identifier",
        "corrective_actions",
        ["identifier"]
    )

    op.create_unique_constraint(
        "uq_audit_answers_identifier",
        "audit_answers",
        ["identifier"]
    )


def downgrade():
    # Drop unique constraints first
    op.drop_constraint(
        "uq_audit_answers_identifier",
        "audit_answers",
        type_="unique"
    )

    op.drop_constraint(
        "uq_corrective_actions_identifier",
        "corrective_actions",
        type_="unique"
    )

    # Drop columns
    op.drop_column("audit_answers", "identifier")
    op.drop_column("corrective_actions", "identifier")