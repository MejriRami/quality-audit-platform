"""Remove pilot_user_id from corrective_actions

Revision ID: b2a82a2db183
Revises: 5ba75c91f351
Create Date: 2025-12-18 10:10:32.170653

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2a82a2db183'
down_revision: Union[str, Sequence[str], None] = '5ba75c91f351'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('corrective_actions', 'pilot_user_id')


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column('corrective_actions', sa.Column('pilot_user_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'corrective_actions', 'users', ['pilot_user_id'], ['id'])
