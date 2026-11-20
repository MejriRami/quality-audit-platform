"""add checklist change requests table

Revision ID: f6a9d8c4e2b1
Revises: f1c2b3a4d5e6
Create Date: 2026-04-22 12:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f6a9d8c4e2b1"
down_revision: Union[str, Sequence[str], None] = "e8f1c2d3b4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "checklist_change_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("questionnaire_id", sa.Integer(), nullable=True),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("requested_by_id", sa.Integer(), nullable=False),
        sa.Column("reviewed_by_id", sa.Integer(), nullable=True),
        sa.Column("request_comment", sa.Text(), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), nullable=False),
        sa.Column("reviewed_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("applied_at", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(["questionnaire_id"], ["questionnaires.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_checklist_change_requests_status_created",
        "checklist_change_requests",
        ["status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_checklist_change_requests_requested_by",
        "checklist_change_requests",
        ["requested_by_id"],
        unique=False,
    )
    op.create_index(
        "ix_checklist_change_requests_questionnaire",
        "checklist_change_requests",
        ["questionnaire_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_checklist_change_requests_questionnaire", table_name="checklist_change_requests")
    op.drop_index("ix_checklist_change_requests_requested_by", table_name="checklist_change_requests")
    op.drop_index("ix_checklist_change_requests_status_created", table_name="checklist_change_requests")
    op.drop_table("checklist_change_requests")
