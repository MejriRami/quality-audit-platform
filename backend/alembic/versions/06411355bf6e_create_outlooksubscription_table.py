"""create OutlookSubscription table

Revision ID: 06411355bf6e
Revises: 397aceed8a8b
Create Date: 2025-12-15 13:26:58.191399

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '06411355bf6e'
down_revision: Union[str, Sequence[str], None] = '397aceed8a8b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'outlook_subscriptions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_email', sa.String(150), nullable=False, unique=True),
        sa.Column('subscription_id', sa.String(255), nullable=False, unique=True),
        sa.Column('expires_at', sa.TIMESTAMP(timezone=True), nullable=False),
    )
    # Optional: add an index for faster queries by user_email
    op.create_index('ix_outlook_subscriptions_user_email', 'outlook_subscriptions', ['user_email'])


def downgrade() -> None:
    op.drop_index(
        'ix_outlook_subscriptions_user_email',
        table_name='outlook_subscriptions',
        if_exists=True,   
    )
    op.drop_table('outlook_subscriptions')
