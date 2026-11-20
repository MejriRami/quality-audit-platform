"""add supervisor_email to audits

Revision ID: 11ea5ca2da24
Revises: 39c600bbb5d5
Create Date: 2026-01-14 15:14:28.831819

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '11ea5ca2da24'
down_revision: Union[str, Sequence[str], None] = '39c600bbb5d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column("audits", sa.Column("supervisor_email", sa.String(length=150), nullable=True))

def downgrade():
    op.drop_column("audits", "supervisor_email")