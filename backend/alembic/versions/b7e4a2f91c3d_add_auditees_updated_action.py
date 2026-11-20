"""add auditees_updated action to audit_action enum

Revision ID: b7e4a2f91c3d
Revises: a3c9d17e4f82
Create Date: 2026-08-07 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b7e4a2f91c3d"
down_revision: Union[str, Sequence[str], None] = "a3c9d17e4f82"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL enum extension: audit_reschedule_history rows only cover
    # reschedules/cancellations today. Auditee-list changes (add/remove
    # participants) are a planning action too but had no history trail —
    # add a dedicated action_type so update_audit_auditees can log them.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_enum e
                JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = 'audit_action' AND e.enumlabel = 'auditees_updated'
            ) THEN
                ALTER TYPE audit_action ADD VALUE 'auditees_updated';
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    # Removing an enum value in PostgreSQL requires rebuilding the type;
    # keeping the value around on downgrade is intentional (safe, non-breaking).
    pass
