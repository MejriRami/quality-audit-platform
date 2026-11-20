"""add_sharepoint_columns_to_document

Revision ID: 559b014d02d0
Revises: e621cb1bb017
Create Date: 2026-01-29 15:52:46.035162

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '559b014d02d0'
down_revision: Union[str, Sequence[str], None] = 'e621cb1bb017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add SharePoint-related columns to documents table
    op.add_column('documents', sa.Column('sharepoint_site_id', sa.String(), nullable=True))
    op.add_column('documents', sa.Column('sharepoint_drive_id', sa.String(), nullable=True))
    op.add_column('documents', sa.Column('sharepoint_item_id', sa.String(), nullable=True))
    op.add_column('documents', sa.Column('sharepoint_path', sa.String(), nullable=True))
    
    # Optional: Add indexes for better query performance
    op.create_index(
        'ix_documents_sharepoint_item_id', 
        'documents', 
        ['sharepoint_item_id'], 
        unique=False
    )
    op.create_index(
        'ix_documents_sharepoint_drive_id', 
        'documents', 
        ['sharepoint_drive_id'], 
        unique=False
    )
    pass


def downgrade() -> None:
    # Drop indexes first
    op.drop_index('ix_documents_sharepoint_drive_id', table_name='documents')
    op.drop_index('ix_documents_sharepoint_item_id', table_name='documents')
    
    # Drop columns
    op.drop_column('documents', 'sharepoint_path')
    op.drop_column('documents', 'sharepoint_item_id')
    op.drop_column('documents', 'sharepoint_drive_id')
    op.drop_column('documents', 'sharepoint_site_id')
