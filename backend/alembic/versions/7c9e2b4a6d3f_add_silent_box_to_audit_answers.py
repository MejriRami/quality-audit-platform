"""add silent_box to audit answers

Revision ID: 7c9e2b4a6d3f
Revises: c36b979cd1ba
Create Date: 2026-07-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c9e2b4a6d3f'
down_revision: Union[str, Sequence[str], None] = 'c36b979cd1ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "audit_answers",
        sa.Column("silent_box", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("audit_answers", "silent_box")
