"""add result class to audits

Revision ID: fd3261252793
Revises: 01acbc45a49f
Create Date: 2026-05-08 14:47:41.533969

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'fd3261252793'
down_revision: Union[str, Sequence[str], None] = '01acbc45a49f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column("audits", sa.Column("result_class", sa.String(length=5), nullable=True))


def downgrade():
    op.drop_column("audits", "result_class")