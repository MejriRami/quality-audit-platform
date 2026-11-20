"""remove customer column from complaints

Revision ID: fd5db3587bcf
Revises: 0129089aebe5
Create Date: 2026-02-05 16:02:42.429565

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fd5db3587bcf'
down_revision: Union[str, Sequence[str], None] = '0129089aebe5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def  upgrade() -> None:
    """
    Supprime la colonne customer de la table complaints.
    Les lignes existantes ne sont PAS supprimées, seule la colonne est retirée.
    """
    op.drop_column('complaints', 'customer')


def downgrade() -> None:
    """
    Rollback : réajoute la colonne customer (mais les données seront perdues)
    """
    op.add_column('complaints', 
                  sa.Column('customer', sa.String(length=100), nullable=True))
