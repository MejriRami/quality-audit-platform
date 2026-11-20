"""placeholder: restore missing revision referenced by a8e2f4c19b7d

Revision ID: e7a1b4c9f3d2
Revises: a3f7c1d29e6b
Create Date: 2026-08-13 00:00:00.000000

a8e2f4c19b7d (add_avo_directory_tables) was pushed with down_revision
pointing at this id, but no file for it was ever committed -- the local
file that presumably created it never made it into the repo. The
production DB was, however, already correctly migrated and stamped to
8f04da99ebe5 (the merge of a8e2f4c19b7d and e2a91c4f7b3d) by the time
this was discovered, and a8e2f4c19b7d's own upgrade() alone fully
accounts for the schema it added (org_directory_members,
org_directory_sync_status, audit_auditees.people_id) -- so nothing here
is covering for an undocumented DDL change. This is a pure no-op that
restores a valid, computable revision graph.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e7a1b4c9f3d2'
down_revision: Union[str, Sequence[str], None] = 'a3f7c1d29e6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
