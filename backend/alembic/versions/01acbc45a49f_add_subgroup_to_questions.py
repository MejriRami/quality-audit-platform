"""add_subgroup_to_questions

Revision ID: 01acbc45a49f
Revises: 657355fbc8c6
Create Date: 2026-05-05 00:05:19.968715

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "01acbc45a49f"
down_revision: Union[str, Sequence[str], None] = "657355fbc8c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- audit_auditees ---
    op.create_index(
        op.f("ix_audit_auditees_id"), "audit_auditees", ["id"], unique=False
    )

    # --- audit_unavailability_access_tokens ---
    op.alter_column(
        "audit_unavailability_access_tokens",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=True,
    )

    # --- audits ---
    op.alter_column(
        "audits",
        "event_created",
        existing_type=sa.BOOLEAN(),
        nullable=True,
        existing_server_default=sa.text("false"),
    )

    # --- car_escalations: drop FK first, then alter column type ---
    op.drop_constraint(
        "car_escalations_email_sent_to_fkey", "car_escalations", type_="foreignkey"
    )
    op.alter_column(
        "car_escalations",
        "email_sent_to",
        existing_type=sa.INTEGER(),
        type_=sa.String(length=150),
        existing_nullable=True,
        postgresql_using="email_sent_to::varchar",
    )

    # --- checklist_change_requests ---
    op.create_index(
        op.f("ix_checklist_change_requests_id"),
        "checklist_change_requests",
        ["id"],
        unique=False,
    )

    # --- corrective_actions_access_tokens ---
    op.alter_column(
        "corrective_actions_access_tokens",
        "corrective_action_id",
        existing_type=sa.INTEGER(),
        nullable=True,
    )
    op.alter_column(
        "corrective_actions_access_tokens",
        "token",
        existing_type=sa.VARCHAR(length=255),
        nullable=True,
    )
    op.alter_column(
        "corrective_actions_access_tokens",
        "expires_at",
        existing_type=postgresql.TIMESTAMP(),
        type_=sa.TIMESTAMP(timezone=True),
        nullable=True,
    )
    op.alter_column(
        "corrective_actions_access_tokens",
        "used",
        existing_type=sa.BOOLEAN(),
        nullable=True,
        existing_server_default=sa.text("false"),
    )
    op.drop_constraint(
        "corrective_actions_access_tokens_token_key",
        "corrective_actions_access_tokens",
        type_="unique",
    )
    op.create_index(
        op.f("ix_corrective_actions_access_tokens_token"),
        "corrective_actions_access_tokens",
        ["token"],
        unique=True,
    )
    op.drop_column("corrective_actions_access_tokens", "created_at")

    # --- corrective_actions_email_otps ---
    op.alter_column(
        "corrective_actions_email_otps",
        "corrective_action_id",
        existing_type=sa.INTEGER(),
        nullable=True,
    )
    op.alter_column(
        "corrective_actions_email_otps",
        "email",
        existing_type=sa.VARCHAR(length=150),
        nullable=True,
    )
    op.alter_column(
        "corrective_actions_email_otps",
        "code",
        existing_type=sa.VARCHAR(length=10),
        type_=sa.String(length=6),
        nullable=True,
    )
    op.alter_column(
        "corrective_actions_email_otps",
        "expires_at",
        existing_type=postgresql.TIMESTAMP(),
        type_=sa.TIMESTAMP(timezone=True),
        nullable=True,
    )
    op.alter_column(
        "corrective_actions_email_otps",
        "verified",
        existing_type=sa.BOOLEAN(),
        nullable=True,
    )
    op.create_index(
        op.f("ix_corrective_actions_email_otps_email"),
        "corrective_actions_email_otps",
        ["email"],
        unique=False,
    )

    # --- email_deliveries ---
    op.create_index(
        op.f("ix_email_deliveries_id"), "email_deliveries", ["id"], unique=False
    )

    # --- notifications ---
    op.create_index(op.f("ix_notifications_id"), "notifications", ["id"], unique=False)

    # --- plant_holidays: constraint already created in d4a9f2e6b7c1, skip if present ---
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_constraints = {
        c["name"] for c in inspector.get_unique_constraints("plant_holidays")
    }
    if "uq_plant_holidays_plant_date" not in existing_constraints:
        op.create_unique_constraint(
            "uq_plant_holidays_plant_date", "plant_holidays", ["plant", "holiday_date"]
        )

    # --- questions: question_code/element/subgroup/is_asterisk are not created by any
    # earlier migration (they were added by hand on some databases), so add them if
    # missing instead of assuming they already exist.
    existing_question_columns = {
        c["name"] for c in inspector.get_columns("questions")
    }

    op.alter_column(
        "questions", "questionnaire_id", existing_type=sa.INTEGER(), nullable=False
    )

    if "question_code" not in existing_question_columns:
        op.add_column(
            "questions", sa.Column("question_code", sa.String(length=100), nullable=True)
        )
    else:
        op.alter_column(
            "questions",
            "question_code",
            existing_type=sa.VARCHAR(length=50),
            type_=sa.String(length=100),
            existing_nullable=True,
        )

    if "element" not in existing_question_columns:
        op.add_column(
            "questions", sa.Column("element", sa.String(length=100), nullable=True)
        )
    else:
        op.alter_column(
            "questions",
            "element",
            existing_type=sa.VARCHAR(length=20),
            type_=sa.String(length=100),
            existing_nullable=True,
        )

    if "subgroup" not in existing_question_columns:
        op.add_column(
            "questions", sa.Column("subgroup", sa.String(length=100), nullable=True)
        )

    if "is_asterisk" not in existing_question_columns:
        op.add_column(
            "questions",
            sa.Column(
                "is_asterisk",
                sa.Boolean(),
                nullable=True,
                server_default=sa.text("false"),
            ),
        )
    else:
        op.alter_column(
            "questions",
            "is_asterisk",
            existing_type=sa.BOOLEAN(),
            nullable=True,
            existing_server_default=sa.text("false"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_question_columns = {
        c["name"] for c in inspector.get_columns("questions")
    }

    # --- questions ---
    if "is_asterisk" in existing_question_columns:
        op.alter_column(
            "questions",
            "is_asterisk",
            existing_type=sa.BOOLEAN(),
            nullable=False,
            existing_server_default=sa.text("false"),
        )
    if "element" in existing_question_columns:
        op.alter_column(
            "questions",
            "element",
            existing_type=sa.String(length=100),
            type_=sa.VARCHAR(length=20),
            existing_nullable=True,
        )
    if "question_code" in existing_question_columns:
        op.alter_column(
            "questions",
            "question_code",
            existing_type=sa.String(length=100),
            type_=sa.VARCHAR(length=50),
            existing_nullable=True,
        )
    op.alter_column(
        "questions", "questionnaire_id", existing_type=sa.INTEGER(), nullable=True
    )

    # --- plant_holidays ---
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_constraints = {
        c["name"] for c in inspector.get_unique_constraints("plant_holidays")
    }
    if "uq_plant_holidays_plant_date" in existing_constraints:
        op.drop_constraint(
            "uq_plant_holidays_plant_date", "plant_holidays", type_="unique"
        )

    # --- notifications ---
    op.drop_index(op.f("ix_notifications_id"), table_name="notifications")

    # --- email_deliveries ---
    op.drop_index(op.f("ix_email_deliveries_id"), table_name="email_deliveries")

    # --- corrective_actions_email_otps ---
    op.drop_index(
        op.f("ix_corrective_actions_email_otps_email"),
        table_name="corrective_actions_email_otps",
    )
    op.alter_column(
        "corrective_actions_email_otps",
        "verified",
        existing_type=sa.BOOLEAN(),
        nullable=False,
    )
    op.alter_column(
        "corrective_actions_email_otps",
        "expires_at",
        existing_type=sa.TIMESTAMP(timezone=True),
        type_=postgresql.TIMESTAMP(),
        nullable=False,
    )
    op.alter_column(
        "corrective_actions_email_otps",
        "code",
        existing_type=sa.String(length=6),
        type_=sa.VARCHAR(length=10),
        nullable=False,
    )
    op.alter_column(
        "corrective_actions_email_otps",
        "email",
        existing_type=sa.VARCHAR(length=150),
        nullable=False,
    )
    op.alter_column(
        "corrective_actions_email_otps",
        "corrective_action_id",
        existing_type=sa.INTEGER(),
        nullable=False,
    )

    # --- corrective_actions_access_tokens ---
    op.add_column(
        "corrective_actions_access_tokens",
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            autoincrement=False,
            nullable=True,
        ),
    )
    op.drop_index(
        op.f("ix_corrective_actions_access_tokens_token"),
        table_name="corrective_actions_access_tokens",
    )
    op.create_unique_constraint(
        "corrective_actions_access_tokens_token_key",
        "corrective_actions_access_tokens",
        ["token"],
    )
    op.alter_column(
        "corrective_actions_access_tokens",
        "used",
        existing_type=sa.BOOLEAN(),
        nullable=False,
        existing_server_default=sa.text("false"),
    )
    op.alter_column(
        "corrective_actions_access_tokens",
        "expires_at",
        existing_type=sa.TIMESTAMP(timezone=True),
        type_=postgresql.TIMESTAMP(),
        nullable=False,
    )
    op.alter_column(
        "corrective_actions_access_tokens",
        "token",
        existing_type=sa.VARCHAR(length=255),
        nullable=False,
    )
    op.alter_column(
        "corrective_actions_access_tokens",
        "corrective_action_id",
        existing_type=sa.INTEGER(),
        nullable=False,
    )

    # --- checklist_change_requests ---
    op.drop_index(
        op.f("ix_checklist_change_requests_id"), table_name="checklist_change_requests"
    )

    # --- car_escalations: alter type back, then restore FK ---
    op.alter_column(
        "car_escalations",
        "email_sent_to",
        existing_type=sa.String(length=150),
        type_=sa.INTEGER(),
        existing_nullable=True,
        postgresql_using="email_sent_to::integer",
    )
    op.create_foreign_key(
        "car_escalations_email_sent_to_fkey",
        "car_escalations",
        "users",
        ["email_sent_to"],
        ["id"],
    )

    # --- audits ---
    op.alter_column(
        "audits",
        "event_created",
        existing_type=sa.BOOLEAN(),
        nullable=False,
        existing_server_default=sa.text("false"),
    )

    # --- audit_unavailability_access_tokens ---
    op.alter_column(
        "audit_unavailability_access_tokens",
        "created_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        nullable=False,
    )

    # --- audit_auditees ---
    op.drop_index(op.f("ix_audit_auditees_id"), table_name="audit_auditees")
