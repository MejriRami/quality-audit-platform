"""add immediate action fields to corrective_actions

Revision ID: a1b2c3d4e5f6
Revises: 01acbc45a49f
Create Date: 2026-05-24 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a1b2c3d4e5f6"
down_revision = "01acbc45a49f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "corrective_actions",
        sa.Column(
            "immediate_action_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "corrective_actions",
        sa.Column("submission_due_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "corrective_actions",
        sa.Column("closure_due_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.alter_column(
        "corrective_actions",
        "immediate_action_required",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("corrective_actions", "closure_due_at")
    op.drop_column("corrective_actions", "submission_due_at")
    op.drop_column("corrective_actions", "immediate_action_required")
