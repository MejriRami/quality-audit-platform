"""add cancel reason code and cancelled action

Revision ID: e8f1c2d3b4a5
Revises: d4a9f2e6b7c1
Create Date: 2026-04-20 09:40:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e8f1c2d3b4a5"
down_revision: Union[str, Sequence[str], None] = "d4a9f2e6b7c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "audit_reschedule_history",
        sa.Column("reason_code", sa.Integer(), nullable=True),
    )

    # PostgreSQL enum extension: add 'cancelled' action if missing.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = 'audit_action' AND e.enumlabel = 'cancelled'
            ) THEN
                ALTER TYPE audit_action ADD VALUE 'cancelled';
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.drop_column("audit_reschedule_history", "reason_code")
    # Keeping enum value 'cancelled' is intentional (safe, non-breaking).
