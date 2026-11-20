"""add event_id column to audits

Revision ID: 397aceed8a8b
Revises: 284d159ceae1
Create Date: 2025-12-05 14:48:23.568079

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '397aceed8a8b'
down_revision: Union[str, Sequence[str], None] = '284d159ceae1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column("audits", sa.Column("event_id", sa.String(200), nullable=True))

def downgrade():
    op.drop_column("audits", "event_id")
