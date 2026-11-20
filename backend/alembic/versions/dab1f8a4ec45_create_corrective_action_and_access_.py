"""create corrective_action and access_token tables

Revision ID: dab1f8a4ec45
Revises: b2a82a2db183
Create Date: 2025-12-19 13:53:25.414453

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'dab1f8a4ec45'
down_revision: Union[str, Sequence[str], None] = 'b2a82a2db183'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade():
    op.create_table(
        "corrective_actions_access_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("corrective_action_id", sa.Integer(), sa.ForeignKey("corrective_actions.id"), nullable=False),
        sa.Column("token", sa.String(length=255), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    op.create_table(
        "corrective_actions_email_otps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("corrective_action_id", sa.Integer(), sa.ForeignKey("corrective_actions.id"), nullable=False),
        sa.Column("email", sa.String(length=150), nullable=False),
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_table("corrective_actions_email_otps")
    op.drop_table("corrective_actions_access_tokens")
