"""add action_type and linked_action_id to corrective_actions

Revision ID: e2a91c4f7b3d
Revises: a3f7c1d29e6b
Create Date: 2026-08-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e2a91c4f7b3d'
down_revision: Union[str, Sequence[str], None] = 'a3f7c1d29e6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column(
        "corrective_actions",
        sa.Column("action_type", sa.String(20), nullable=False, server_default="corrective"),
    )
    op.add_column(
        "corrective_actions",
        sa.Column("linked_action_id", sa.Integer(), sa.ForeignKey("corrective_actions.id"), nullable=True),
    )
    op.alter_column("corrective_actions", "action_type", server_default=None)


def downgrade():
    op.drop_column("corrective_actions", "linked_action_id")
    op.drop_column("corrective_actions", "action_type")
