"""rename metadata column to meta_data

Revision ID: 35ba4674563d
Revises: 6fc65fb0f27f
Create Date: 2025-12-25 10:11:51.538321

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '35ba4674563d'
down_revision: Union[str, Sequence[str], None] = '6fc65fb0f27f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # For PostgreSQL
    op.alter_column('notifications', 'metadata', new_column_name='meta_data')
    


def downgrade():
    op.alter_column('notifications', 'meta_data', new_column_name='metadata')