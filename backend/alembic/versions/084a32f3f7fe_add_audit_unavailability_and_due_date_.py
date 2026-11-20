"""add audit_unavailability and due_date_base

Revision ID: 084a32f3f7fe
Revises: e797b0411bb4
Create Date: 2025-12-23 09:42:23.418805

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '084a32f3f7fe'
down_revision: Union[str, Sequence[str], None] = 'e797b0411bb4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # Create audit_unavailability table
    op.create_table(
        "audit_unavailability",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("audit_id", sa.Integer(), sa.ForeignKey("audits.id"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"))
    )

    # Add due_date_base column to corrective_actions
    op.add_column(
        "corrective_actions",
        sa.Column("due_date_base", sa.Date(), nullable=True),
    )


def downgrade():
    # Remove due_date_base column
    op.drop_column("corrective_actions", "due_date_base")

    # Drop audit_unavailability table
    op.drop_table("audit_unavailability")
