"""add active in user

Revision ID: ef0970813dc9
Revises: b37a43201aa5
Create Date: 2025-11-28 10:26:47.809574

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ef0970813dc9'
down_revision: Union[str, Sequence[str], None] = 'b37a43201aa5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("active", sa.Boolean(), server_default="true"))
    


def downgrade() -> None:
    op.drop_column("users", "active")
