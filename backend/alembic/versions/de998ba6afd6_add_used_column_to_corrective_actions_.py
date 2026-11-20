"""Add used column to corrective_actions_access_tokens

Revision ID: de998ba6afd6
Revises: dab1f8a4ec45
Create Date: 2025-12-19 14:01:21.968041

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'de998ba6afd6'
down_revision: Union[str, Sequence[str], None] = 'dab1f8a4ec45'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column(
        "corrective_actions_access_tokens",
        sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.false())
    )

def downgrade():
    op.drop_column("corrective_actions_access_tokens", "used")

