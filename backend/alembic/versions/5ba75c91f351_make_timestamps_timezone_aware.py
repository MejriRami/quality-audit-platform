"""make timestamps timezone-aware

Revision ID: 5ba75c91f351
Revises: c408306b148a
Create Date: 2025-12-16 16:20:01.161209

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5ba75c91f351'
down_revision: Union[str, Sequence[str], None] = 'c408306b148a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "audit_answers",
        "created_at",
        type_=sa.TIMESTAMP(timezone=True),
        existing_type=sa.TIMESTAMP(timezone=False),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
        existing_nullable=True,
    )

    op.alter_column(
        "corrective_actions",
        "created_at",
        type_=sa.TIMESTAMP(timezone=True),
        existing_type=sa.TIMESTAMP(timezone=False),
        postgresql_using="created_at AT TIME ZONE 'UTC'",
        existing_nullable=True,
    )

    op.alter_column(
        "documents",
        "uploaded_at",
        type_=sa.TIMESTAMP(timezone=True),
        existing_type=sa.TIMESTAMP(timezone=False),
        postgresql_using="uploaded_at AT TIME ZONE 'UTC'",
        existing_nullable=True,
    )



def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "audit_answers",
        "created_at",
        type_=sa.TIMESTAMP(timezone=False),
        existing_type=sa.TIMESTAMP(timezone=True),
        postgresql_using="timezone('UTC', created_at)",
        existing_nullable=True,
    )

    op.alter_column(
        "corrective_actions",
        "created_at",
        type_=sa.TIMESTAMP(timezone=False),
        existing_type=sa.TIMESTAMP(timezone=True),
        postgresql_using="timezone('UTC', created_at)",
        existing_nullable=True,
    )

    op.alter_column(
        "documents",
        "uploaded_at",
        type_=sa.TIMESTAMP(timezone=False),
        existing_type=sa.TIMESTAMP(timezone=True),
        postgresql_using="timezone('UTC', uploaded_at)",
        existing_nullable=True,
    )
