"""add audit_unavailability_access_tokens

Revision ID: 00d6d3166331
Revises: 084a32f3f7fe
Create Date: 2025-12-23 10:57:38.880546

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP
from datetime import datetime

# revision identifiers, used by Alembic.
revision: str = '00d6d3166331'
down_revision: Union[str, Sequence[str], None] = '084a32f3f7fe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_table(
        'audit_unavailability_access_tokens',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('audit_id', sa.Integer, sa.ForeignKey('audits.id'), nullable=False),
        sa.Column('email', sa.String(150), nullable=False, index=True),
        sa.Column('token', sa.String(64), nullable=False, unique=True, index=True),
        sa.Column('expires_at', TIMESTAMP(timezone=True), nullable=False),
        sa.Column('used', sa.Boolean, default=False),
        sa.Column('created_at', TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    )


def downgrade():
    op.drop_table('audit_unavailability_access_tokens')
