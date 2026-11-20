"""add received_webhooks table

Revision ID: 32811c1a2cba
Revises: fd5db3587bcf
Create Date: 2026-03-13 10:09:02.855429

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '32811c1a2cba'
down_revision: Union[str, Sequence[str], None] = 'fd5db3587bcf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "received_webhooks",
        sa.Column("id",              sa.Integer(),     primary_key=True, autoincrement=True),
        sa.Column("delivery_id",     sa.String(36),    nullable=False),
        sa.Column("event",           sa.String(100),   nullable=False),
        sa.Column("complaint_id",    sa.Integer(),     nullable=True),
        sa.Column("complaint_ref",   sa.String(50),    nullable=True),
        sa.Column("complaint_type",  sa.String(50),    nullable=True),
        sa.Column("payload_json",    sa.Text(),        nullable=False),
        sa.Column("signature_valid", sa.Boolean(),     nullable=False, server_default="true"),
        sa.Column("received_at",     sa.DateTime(),    nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_received_webhooks_delivery_id",
                    "received_webhooks", ["delivery_id"], unique=True)
    op.create_index("ix_received_webhooks_complaint_id",
                    "received_webhooks", ["complaint_id"])
    op.create_index("ix_received_webhooks_complaint_ref",
                    "received_webhooks", ["complaint_ref"])
    op.create_index("ix_received_webhooks_received_at",
                    "received_webhooks", ["received_at"])
 
 
def downgrade() -> None:
    op.drop_index("ix_received_webhooks_delivery_id",   table_name="received_webhooks")
    op.drop_index("ix_received_webhooks_complaint_id",  table_name="received_webhooks")
    op.drop_index("ix_received_webhooks_complaint_ref", table_name="received_webhooks")
    op.drop_index("ix_received_webhooks_received_at",   table_name="received_webhooks")
    op.drop_table("received_webhooks")
