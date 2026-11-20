"""merge avo directory and car action_type heads

Revision ID: 8f04da99ebe5
Revises: a8e2f4c19b7d, e2a91c4f7b3d
Create Date: 2026-08-13 15:01:44.279429

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8f04da99ebe5'
down_revision: Union[str, Sequence[str], None] = ('a8e2f4c19b7d', 'e2a91c4f7b3d')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
