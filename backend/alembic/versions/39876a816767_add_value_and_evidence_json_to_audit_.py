"""add value and evidence_json to audit_answer_requirements

Revision ID: 39876a816767
Revises: 351f1a27805b
Create Date: 2026-07-16 17:36:19.863104

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '39876a816767'
down_revision: Union[str, Sequence[str], None] = '351f1a27805b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "audit_answer_requirements",
        sa.Column("value", sa.Float(), nullable=True),
    )
    op.add_column(
        "audit_answer_requirements",
        sa.Column("evidence_json", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("audit_answer_requirements", "evidence_json")
    op.drop_column("audit_answer_requirements", "value")
