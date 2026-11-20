"""merge heads

Revision ID: 2f040c4ee76c
Revises: 2561badc3326, ddc318c25da8
Create Date: 2025-12-05 08:29:31.244984

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2f040c4ee76c'
down_revision: Union[str, Sequence[str], None] = ('2561badc3326', 'ddc318c25da8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
