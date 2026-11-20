"""merge teammate and local heads

Revision ID: 351f1a27805b
Revises: a1b2c3d4e5f6, b4c5d6e7f8a9
Create Date: 2026-06-01 16:27:17.028136

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '351f1a27805b'
down_revision: Union[str, Sequence[str], None] = ('a1b2c3d4e5f6', 'b4c5d6e7f8a9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
