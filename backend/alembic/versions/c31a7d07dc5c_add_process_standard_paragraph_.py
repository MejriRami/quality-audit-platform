"""Add process, standard_paragraph, classification columns to audit_answers

Revision ID: c31a7d07dc5c
Revises: ee697783e57d
Create Date: 2026-01-15 08:12:47.183484

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c31a7d07dc5c'
down_revision: Union[str, Sequence[str], None] = 'ee697783e57d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # op.add_column('audit_answers', sa.Column('process', sa.String(), nullable=True))
    # op.add_column('audit_answers', sa.Column('standard_paragraph', sa.String(), nullable=True))
    # op.add_column('audit_answers', sa.Column('classification', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('audit_answers', 'classification')
    op.drop_column('audit_answers', 'standard_paragraph')
    op.drop_column('audit_answers', 'process')