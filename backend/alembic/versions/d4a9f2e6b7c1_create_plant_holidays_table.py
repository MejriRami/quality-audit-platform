"""create plant holidays table

Revision ID: d4a9f2e6b7c1
Revises: c1e6a2b7f9d1
Create Date: 2026-04-17 11:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4a9f2e6b7c1"
down_revision: Union[str, Sequence[str], None] = "c1e6a2b7f9d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("plant_holidays"):
        op.create_table(
            "plant_holidays",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("plant", sa.String(length=80), nullable=False),
            sa.Column("holiday_date", sa.Date(), nullable=False),
            sa.Column("name", sa.String(length=150), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("plant", "holiday_date", name="uq_plant_holidays_plant_date"),
        )

    existing_indexes = {idx["name"] for idx in inspector.get_indexes("plant_holidays")}
    if "ix_plant_holidays_id" not in existing_indexes:
        op.create_index("ix_plant_holidays_id", "plant_holidays", ["id"], unique=False)
    if "ix_plant_holidays_plant" not in existing_indexes:
        op.create_index("ix_plant_holidays_plant", "plant_holidays", ["plant"], unique=False)
    if "ix_plant_holidays_holiday_date" not in existing_indexes:
        op.create_index(
            "ix_plant_holidays_holiday_date",
            "plant_holidays",
            ["holiday_date"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("plant_holidays"):
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("plant_holidays")}
        if "ix_plant_holidays_holiday_date" in existing_indexes:
            op.drop_index("ix_plant_holidays_holiday_date", table_name="plant_holidays")
        if "ix_plant_holidays_plant" in existing_indexes:
            op.drop_index("ix_plant_holidays_plant", table_name="plant_holidays")
        if "ix_plant_holidays_id" in existing_indexes:
            op.drop_index("ix_plant_holidays_id", table_name="plant_holidays")
        op.drop_table("plant_holidays")
