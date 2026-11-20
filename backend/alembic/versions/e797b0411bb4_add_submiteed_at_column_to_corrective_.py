"""Add submiteed_at column to corrective_actions

Revision ID: e797b0411bb4
Revises: 9bbe8009adc4
Create Date: 2025-12-19 15:15:54.518584

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e797b0411bb4'
down_revision: Union[str, Sequence[str], None] = '9bbe8009adc4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade():
    op.add_column(
        "corrective_actions",
        sa.Column("submitted_at", sa.TIMESTAMP(timezone=True), nullable=True)
    )


def downgrade():
    op.drop_column("corrective_actions", "submitted_at")