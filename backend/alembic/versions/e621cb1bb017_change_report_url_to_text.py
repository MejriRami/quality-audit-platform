"""change report_url to Text

Revision ID: e621cb1bb017
Revises: 6da5315c52bf
Create Date: 2026-01-28 16:41:33.762320

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e621cb1bb017'
down_revision: Union[str, Sequence[str], None] = '6da5315c52bf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
     op.alter_column(
        "audits",
        "report_url",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade():
    op.alter_column(
        "audits",
        "report_url",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=True,
    )