"""add kpi chatbot messages table

Revision ID: e4f1a3c8d2b7
Revises: d8e2f4a6b9c3
Create Date: 2026-07-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4f1a3c8d2b7'
down_revision: Union[str, Sequence[str], None] = 'd8e2f4a6b9c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "kpi_chatbot_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_kpi_chatbot_messages_user_id",
        "kpi_chatbot_messages",
        ["user_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_kpi_chatbot_messages_user_id", table_name="kpi_chatbot_messages")
    op.drop_table("kpi_chatbot_messages")
