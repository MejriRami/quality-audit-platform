"""add audit_answer_requirement_id to corrective_actions

Revision ID: a7c3e5f19b20
Revises: e2f3a4b5c6d7
Create Date: 2026-09-28 10:00:00.000000

VDA sub-requirements scored 0/4/6/8 now raise their own CAR (previously only
the parent question did, so requirement findings silently produced no
non-conformity). The link identifies which requirement a CAR belongs to.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7c3e5f19b20"
down_revision: Union[str, Sequence[str], None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "corrective_actions",
        sa.Column("audit_answer_requirement_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_corrective_actions_audit_answer_requirement_id",
        "corrective_actions",
        "audit_answer_requirements",
        ["audit_answer_requirement_id"],
        ["id"],
    )
    op.create_index(
        "ix_corrective_actions_audit_answer_requirement_id",
        "corrective_actions",
        ["audit_answer_requirement_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_corrective_actions_audit_answer_requirement_id",
        table_name="corrective_actions",
    )
    op.drop_constraint(
        "fk_corrective_actions_audit_answer_requirement_id",
        "corrective_actions",
        type_="foreignkey",
    )
    op.drop_column("corrective_actions", "audit_answer_requirement_id")
