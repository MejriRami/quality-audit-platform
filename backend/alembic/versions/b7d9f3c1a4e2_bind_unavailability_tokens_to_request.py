"""bind unavailability access tokens to specific request

Revision ID: b7d9f3c1a4e2
Revises: a9f4c1b8d2e7
Create Date: 2026-04-15 14:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7d9f3c1a4e2"
down_revision: Union[str, Sequence[str], None] = "a9f4c1b8d2e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "audit_unavailability_access_tokens",
        sa.Column("unavailability_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_audit_unavailability_access_tokens_unavailability_id",
        "audit_unavailability_access_tokens",
        ["unavailability_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_audit_unavailability_access_tokens_unavailability_id",
        "audit_unavailability_access_tokens",
        "audit_unavailability",
        ["unavailability_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_audit_unavailability_access_tokens_unavailability_id",
        "audit_unavailability_access_tokens",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_audit_unavailability_access_tokens_unavailability_id",
        table_name="audit_unavailability_access_tokens",
    )
    op.drop_column("audit_unavailability_access_tokens", "unavailability_id")

