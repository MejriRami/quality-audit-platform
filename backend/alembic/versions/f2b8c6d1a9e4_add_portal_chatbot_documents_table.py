"""add portal chatbot documents table

Revision ID: f2b8c6d1a9e4
Revises: e4f1a3c8d2b7
Create Date: 2026-07-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2b8c6d1a9e4'
down_revision: Union[str, Sequence[str], None] = 'e4f1a3c8d2b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "portal_chatbot_documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plant", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=150), nullable=False),
        sa.Column("access_mode", sa.String(length=20), nullable=False),
        sa.Column(
            "car_id",
            sa.Integer(),
            sa.ForeignKey("corrective_actions.id"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("blob_name", sa.String(length=500), nullable=False),
        sa.Column("file_url", sa.Text(), nullable=False),
        sa.Column("mimetype", sa.String(length=100), nullable=True),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("truncated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index(
        "ix_portal_chatbot_documents_identity",
        "portal_chatbot_documents",
        ["plant", "email", "access_mode", "car_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_portal_chatbot_documents_identity", table_name="portal_chatbot_documents")
    op.drop_table("portal_chatbot_documents")
