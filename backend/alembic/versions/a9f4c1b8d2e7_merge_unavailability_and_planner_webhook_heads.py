"""merge unavailability and planner webhook heads

Revision ID: a9f4c1b8d2e7
Revises: f1c2b3a4d5e6, 32811c1a2cba
Create Date: 2026-04-15 12:30:00.000000

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "a9f4c1b8d2e7"
down_revision: Union[str, Sequence[str], None] = ("f1c2b3a4d5e6", "32811c1a2cba")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
