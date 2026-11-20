"""add finding to corrective_actions

Revision ID: a3f7c1d29e6b
Revises: b7e4a2f91c3d
Create Date: 2026-08-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a3f7c1d29e6b'
down_revision: Union[str, Sequence[str], None] = 'c1e8f3a5b7d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column("corrective_actions", sa.Column("finding", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("corrective_actions", "finding")
