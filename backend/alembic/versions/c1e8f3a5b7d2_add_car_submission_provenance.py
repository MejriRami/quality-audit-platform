"""add car submission provenance (submitted_by_email, submission_channel)

Revision ID: c1e8f3a5b7d2
Revises: b7e4a2f91c3d
Create Date: 2026-08-10 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c1e8f3a5b7d2"
down_revision: Union[str, Sequence[str], None] = "b7e4a2f91c3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Any invited auditee on an audit can submit any of its CARs (see
    # verify_email_for_car), so car.auditee_id alone doesn't tell you who
    # actually submitted — record it explicitly at submit time, along with
    # whether it came through the portal or the standalone emailed link.
    op.add_column(
        "corrective_actions",
        sa.Column("submitted_by_email", sa.String(length=150), nullable=True),
    )
    op.add_column(
        "corrective_actions",
        sa.Column("submission_channel", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("corrective_actions", "submission_channel")
    op.drop_column("corrective_actions", "submitted_by_email")
