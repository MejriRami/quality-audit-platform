"""add verified to corrective_actions_email_otps

Revision ID: 9bbe8009adc4
Revises: de998ba6afd6
Create Date: 2025-12-19 14:25:21.260999

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9bbe8009adc4'
down_revision: Union[str, Sequence[str], None] = 'de998ba6afd6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


 

def upgrade():
    op.add_column(
        "corrective_actions_email_otps",
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.text("false"))
    )
    # optionnel: retirer le default côté DB après remplissage
    op.alter_column("corrective_actions_email_otps", "verified", server_default=None)

def downgrade():
    op.drop_column("corrective_actions_email_otps", "verified")
