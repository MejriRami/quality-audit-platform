"""add audit_auditees table and remove auditee_id

Revision ID: 92d7bd2ad69a
Revises: 2f040c4ee76c
Create Date: 2025-12-05 08:29:39.591962

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '92d7bd2ad69a'
down_revision: Union[str, Sequence[str], None] = '2f040c4ee76c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    # 1. Create new table
    op.create_table(
        'audit_auditees',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('audit_id', sa.Integer(), sa.ForeignKey('audits.id', ondelete='CASCADE')),
        sa.Column('email', sa.String(150), nullable=False)
    )

    # 2. Drop old column
    op.drop_constraint('audits_auditee_id_fkey', 'audits', type_='foreignkey')
    op.drop_column('audits', 'auditee_id')



def downgrade():
    # 1. Re-add old column
    op.add_column('audits', sa.Column('auditee_id', sa.Integer()))
    op.create_foreign_key(
        'audits_auditee_id_fkey',
        'audits', 'users',
        ['auditee_id'], ['id']
    )

    # 2. Drop new table
    op.drop_table('audit_auditees')
