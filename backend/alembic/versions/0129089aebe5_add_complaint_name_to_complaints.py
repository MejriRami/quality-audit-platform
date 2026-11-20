"""add complaint_name to complaints

Revision ID: 0129089aebe5
Revises: 6133d94b14b9
Create Date: 2026-02-05 14:50:34.417462

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0129089aebe5'
down_revision: Union[str, Sequence[str], None] = '6133d94b14b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('complaints', sa.Column('complaint_name', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('complaints', 'complaint_name')
