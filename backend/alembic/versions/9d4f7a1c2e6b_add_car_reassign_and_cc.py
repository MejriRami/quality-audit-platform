"""add car reassign and cc fields

Revision ID: 9d4f7a1c2e6b
Revises: 7c9e2b4a6d3f
Create Date: 2026-07-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9d4f7a1c2e6b'
down_revision: Union[str, Sequence[str], None] = '7c9e2b4a6d3f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "corrective_actions",
        sa.Column("reassigned_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "corrective_actions",
        sa.Column("reassigned_from_email", sa.String(length=150), nullable=True),
    )
    op.add_column(
        "corrective_actions",
        sa.Column("reassignment_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "corrective_actions",
        sa.Column("cc_emails", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("corrective_actions", "cc_emails")
    op.drop_column("corrective_actions", "reassignment_reason")
    op.drop_column("corrective_actions", "reassigned_from_email")
    op.drop_column("corrective_actions", "reassigned_at")
