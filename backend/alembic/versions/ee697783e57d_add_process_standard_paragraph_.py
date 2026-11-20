"""Add process, standard_paragraph, classification columns to audit_answers

Revision ID: ee697783e57d
Revises: 11ea5ca2da24
Create Date: 2026-01-15 08:12:15.575222

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ee697783e57d'
down_revision: Union[str, Sequence[str], None] = '11ea5ca2da24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add new columns
    op.add_column('audit_answers', sa.Column('process', sa.String(), nullable=True))
    op.add_column('audit_answers', sa.Column('standard_paragraph', sa.String(), nullable=True))
    op.add_column('audit_answers', sa.Column('classification', sa.String(), nullable=True))
    
    # Make question_id nullable
    op.alter_column('audit_answers', 'question_id',
                    existing_type=sa.Integer(),
                    nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    # Make question_id NOT nullable again
    op.alter_column('audit_answers', 'question_id',
                    existing_type=sa.Integer(),
                    nullable=False)
    
    # Drop new columns
    op.drop_column('audit_answers', 'classification')
    op.drop_column('audit_answers', 'standard_paragraph')
    op.drop_column('audit_answers', 'process')
