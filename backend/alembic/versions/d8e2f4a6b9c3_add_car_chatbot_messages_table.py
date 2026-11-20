"""add portal chatbot messages table

Revision ID: d8e2f4a6b9c3
Revises: c1a8f5e3b7d2
Create Date: 2026-07-28 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8e2f4a6b9c3'
down_revision: Union[str, Sequence[str], None] = 'c1a8f5e3b7d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "portal_chatbot_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plant", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=150), nullable=False),
        sa.Column("access_mode", sa.String(length=20), nullable=False),
        sa.Column(
            "car_id",
            sa.Integer(),
            sa.ForeignKey("corrective_actions.id"),
            nullable=True,
        ),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_portal_chatbot_messages_identity",
        "portal_chatbot_messages",
        ["plant", "email", "access_mode"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_portal_chatbot_messages_identity", table_name="portal_chatbot_messages")
    op.drop_table("portal_chatbot_messages")
