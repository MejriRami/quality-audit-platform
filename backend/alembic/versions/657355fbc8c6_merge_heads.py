"""merge_heads

Revision ID: 657355fbc8c6
Revises: 7b3f2a9d11c4, f6a9d8c4e2b1
Create Date: 2026-05-04 23:55:18.274472

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '657355fbc8c6'
down_revision: Union[str, Sequence[str], None] = ('7b3f2a9d11c4', 'f6a9d8c4e2b1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
