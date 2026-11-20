"""fix portal_chatbot_messages schema drift

Revision ID: a3c9d17e4f82
Revises: f2b8c6d1a9e4
Create Date: 2026-08-05 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3c9d17e4f82'
down_revision: Union[str, Sequence[str], None] = 'f2b8c6d1a9e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # An earlier draft of d8e2f4a6b9c3 (before it was rewritten to match the
    # final PortalChatbotMessage model — plant/email/access_mode identity,
    # not corrective_action_id-only) was already applied to production
    # before the rewrite. Alembic tracks applied revisions by ID, not
    # content, so it never re-ran and production was left with the old
    # car_chatbot_messages table instead of portal_chatbot_messages. It was
    # never populated (0 rows) — safe to drop outright rather than migrate
    # data.
    #
    # IF EXISTS: this drift only happened on environments where that old
    # draft actually ran (production). Anywhere else — a fresh local DB, a
    # new environment built from this migration chain — the table was never
    # created, so an unconditional DROP TABLE fails there for a reason that
    # has nothing to do with that environment's own state.
    op.execute(sa.text("DROP TABLE IF EXISTS car_chatbot_messages"))

    # IF NOT EXISTS for the same reason as the drop above: on an environment
    # where this migration was already partially applied (or the table was
    # otherwise created ahead of Alembic tracking it), re-running the plain
    # CREATE would fail on a table that's already in the right shape.
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS portal_chatbot_messages (
            id SERIAL PRIMARY KEY,
            plant VARCHAR(100) NOT NULL,
            email VARCHAR(150) NOT NULL,
            access_mode VARCHAR(20) NOT NULL,
            car_id INTEGER REFERENCES corrective_actions(id),
            role VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_portal_chatbot_messages_identity "
        "ON portal_chatbot_messages (plant, email, access_mode)"
    ))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_portal_chatbot_messages_identity", table_name="portal_chatbot_messages")
    op.drop_table("portal_chatbot_messages")
