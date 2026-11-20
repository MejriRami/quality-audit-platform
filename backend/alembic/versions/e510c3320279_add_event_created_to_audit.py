"""add event_created to audit

Revision ID: e510c3320279
Revises: 92d7bd2ad69a
Create Date: 2025-12-05 10:00:32.690263

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e510c3320279'
down_revision: Union[str, Sequence[str], None] = '92d7bd2ad69a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
     #Add a new boolean column, default False
    op.add_column('audits', sa.Column('event_created', sa.Boolean(), nullable=False, server_default=sa.sql.expression.false()))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('audits', 'event_created')

