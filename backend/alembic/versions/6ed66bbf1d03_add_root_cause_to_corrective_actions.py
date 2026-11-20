"""add root_cause to corrective_actions

Revision ID: 6ed66bbf1d03
Revises: 35ba4674563d
Create Date: 2026-01-07 10:12:04.776308

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '6ed66bbf1d03'
down_revision: Union[str, Sequence[str], None] = '35ba4674563d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column(
        "corrective_actions",
        sa.Column("root_cause", sa.Text(), nullable=True)
    )


def downgrade():
    op.drop_column("corrective_actions", "root_cause")