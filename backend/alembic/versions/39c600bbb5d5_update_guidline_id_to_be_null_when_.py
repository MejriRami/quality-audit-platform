"""update guidline id to be null when deleting document

Revision ID: 39c600bbb5d5
Revises: 6ed66bbf1d03
Create Date: 2026-01-09 10:53:37.289146

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '39c600bbb5d5'
down_revision: Union[str, Sequence[str], None] = '6ed66bbf1d03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.drop_constraint(
        "questionnaires_guideline_id_fkey",
        "questionnaires",
        type_="foreignkey"
    )
    op.create_foreign_key(
        "questionnaires_guideline_id_fkey",
        "questionnaires",
        "documents",
        ["guideline_id"],
        ["id"],
        ondelete="SET NULL"
    )


def downgrade():
    op.drop_constraint(
        "questionnaires_guideline_id_fkey",
        "questionnaires",
        type_="foreignkey"
    )
    op.create_foreign_key(
        "questionnaires_guideline_id_fkey",
        "questionnaires",
        "documents",
        ["guideline_id"],
        ["id"]
    )