"""add vda requirements tables

Revision ID: 7b3f2a9d11c4
Revises: fd5db3587bcf
Create Date: 2026-05-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7b3f2a9d11c4"
down_revision: Union[str, Sequence[str], None] = "fd5db3587bcf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "question_requirements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("requirement_code", sa.String(length=100), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_question_requirements_question_id",
        "question_requirements",
        ["question_id"],
        unique=False,
    )
    op.create_index(
        "ix_question_requirements_question_req_code",
        "question_requirements",
        ["question_id", "requirement_code"],
        unique=False,
    )

    op.create_table(
        "audit_answer_requirements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("audit_answer_id", sa.Integer(), nullable=False),
        sa.Column("question_requirement_id", sa.Integer(), nullable=False),
        sa.Column("fulfilled", sa.Boolean(), nullable=True),
        sa.Column("finding_text", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["audit_answer_id"], ["audit_answers.id"]),
        sa.ForeignKeyConstraint(["question_requirement_id"], ["question_requirements.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_answer_requirements_audit_answer_id",
        "audit_answer_requirements",
        ["audit_answer_id"],
        unique=False,
    )
    op.create_index(
        "ix_audit_answer_requirements_question_requirement_id",
        "audit_answer_requirements",
        ["question_requirement_id"],
        unique=False,
    )
    op.create_index(
        "ix_audit_answer_requirements_unique_link",
        "audit_answer_requirements",
        ["audit_answer_id", "question_requirement_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_audit_answer_requirements_unique_link", table_name="audit_answer_requirements")
    op.drop_index("ix_audit_answer_requirements_question_requirement_id", table_name="audit_answer_requirements")
    op.drop_index("ix_audit_answer_requirements_audit_answer_id", table_name="audit_answer_requirements")
    op.drop_table("audit_answer_requirements")

    op.drop_index("ix_question_requirements_question_req_code", table_name="question_requirements")
    op.drop_index("ix_question_requirements_question_id", table_name="question_requirements")
    op.drop_table("question_requirements")
