"""add auditor_chatbot_messages

Revision ID: b4e8d2c61f07
Revises: a7c3e5f19b20
Create Date: 2026-09-29 10:00:00.000000

Conversation history for the auditor assistant (the auditee portal has its
own portal_chatbot_messages, keyed by portal identity rather than user).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b4e8d2c61f07"
down_revision: Union[str, Sequence[str], None] = "a7c3e5f19b20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auditor_chatbot_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_auditor_chatbot_messages_user_id", "auditor_chatbot_messages", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_auditor_chatbot_messages_user_id", "auditor_chatbot_messages")
    op.drop_table("auditor_chatbot_messages")
