"""add audit_number to audits

Revision ID: 284d159ceae1
Revises: e510c3320279
Create Date: 2025-12-05 11:47:21.504368

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy as sa
from sqlalchemy.sql import table, column


# revision identifiers, used by Alembic.
revision: str = '284d159ceae1'
down_revision: Union[str, Sequence[str], None] = 'e510c3320279'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.add_column('audits', sa.Column('audit_number', sa.String(length=20), nullable=True, unique=True))

    audits_table = table('audits', column('id', sa.Integer), column('audit_number', sa.String))
    connection = op.get_bind()

    # Correct select usage
    result = connection.execute(sa.select(audits_table.c.id))
    for row in result:
        audit_number = f"A-{row.id:05d}"
        connection.execute(
            audits_table.update().where(audits_table.c.id == row.id).values(audit_number=audit_number)
        )

    op.alter_column('audits', 'audit_number', nullable=False)
def downgrade():
    op.drop_column('audits', 'audit_number')
