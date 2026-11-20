"""add second_auditor_id to audits

Revision ID: c4d2a8e6f1b3
Revises: b4e8d2c61f07
Create Date: 2026-10-07 10:00:00.000000

Optional co-auditor on an audit. auditor_id remains the lead auditor.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d2a8e6f1b3"
down_revision: Union[str, Sequence[str], None] = "b4e8d2c61f07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "audits",
        sa.Column(
            "second_auditor_id",
            sa.Integer(),
            sa.ForeignKey(
                "users.id",
                name="fk_audits_second_auditor_id_users",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_audits_second_auditor_id", "audits", ["second_auditor_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_audits_second_auditor_id", table_name="audits")
    op.drop_constraint(
        "fk_audits_second_auditor_id_users", "audits", type_="foreignkey"
    )
    op.drop_column("audits", "second_auditor_id")
