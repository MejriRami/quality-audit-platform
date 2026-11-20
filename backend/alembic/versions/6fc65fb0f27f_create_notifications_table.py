"""create notifications table

Revision ID: 6fc65fb0f27f
Revises: 00d6d3166331
Create Date: 2025-12-25 10:09:31.919680

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6fc65fb0f27f'
down_revision: Union[str, Sequence[str], None] = '00d6d3166331'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade():
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(50), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('link', sa.String(255), nullable=True),
        sa.Column('read', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('metadata', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    op.create_index('idx_notification_user_read', 'notifications', ['user_id', 'read'])
    op.create_index('idx_notification_user_created', 'notifications', ['user_id', 'created_at'])

def downgrade():
    op.drop_index('idx_notification_user_created', 'notifications')
    op.drop_index('idx_notification_user_read', 'notifications')
    op.drop_table('notifications')
