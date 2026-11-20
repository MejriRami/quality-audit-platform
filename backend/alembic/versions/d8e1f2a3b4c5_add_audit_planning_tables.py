"""add monthly audit planning tables

Revision ID: d8e1f2a3b4c5
Revises: c65c9ba3e00c
Create Date: 2026-09-24 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d8e1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "c65c9ba3e00c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# From the audit priorities table (P8).
DEFAULT_SUPPORT_PROCESSES = [
    "Manufacturing Process Map",
    "HR",
    "Maintenance",
    "IT",
    "Supply Chain",
    "Audit",
    "Leadership",
]



def upgrade() -> None:
    support = op.create_table(
        "audit_plan_support_processes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.bulk_insert(
        support,
        [
            {"name": name, "is_active": True, "sort_order": i}
            for i, name in enumerate(DEFAULT_SUPPORT_PROCESSES, start=1)
        ],
    )

    op.create_table(
        "audit_plan_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_month", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("check_status", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("warnings", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("generated_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("approved_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
    )
    op.create_index("ix_audit_plan_runs_plan_month", "audit_plan_runs", ["plan_month"])
    # At most one approved plan per month.
    op.create_index(
        "uq_audit_plan_runs_approved_month",
        "audit_plan_runs",
        ["plan_month"],
        unique=True,
        postgresql_where=sa.text("status = 'approved'"),
    )

    op.create_table(
        "audit_plan_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("audit_plan_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plant", sa.String(length=80), nullable=False),
        sa.Column("product_line", sa.String(length=120)),
        sa.Column("project_code", sa.String(length=80)),
        sa.Column(
            "support_process_id",
            sa.Integer(),
            sa.ForeignKey("audit_plan_support_processes.id", ondelete="SET NULL"),
        ),
        sa.Column("trigger_codes", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("checklist", sa.String(length=120), nullable=False),
        sa.Column("history_kind", sa.String(length=30), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("complaint_volume", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("status_reason", sa.Text()),
        sa.Column("scheduled_date", sa.Date()),
        sa.Column("auditor_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("auditee_role", sa.String(length=80), nullable=False),
        sa.Column("auditee_name", sa.String(length=200)),
        sa.Column("auditee_email", sa.String(length=150)),
        sa.Column("auditee_status", sa.String(length=30), nullable=False),
        sa.Column("auditee_note", sa.Text()),
        sa.Column("overridden", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("override_note", sa.Text()),
        sa.Column("completed_on", sa.Date()),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_plan_items_run_id", "audit_plan_items", ["run_id"])
    op.create_index("ix_audit_plan_items_plant", "audit_plan_items", ["plant"])
    op.create_index("ix_audit_plan_items_scheduled_date", "audit_plan_items", ["scheduled_date"])

    op.create_table(
        "audit_plan_customer_escalations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plant", sa.String(length=80), nullable=False),
        sa.Column("product_line", sa.String(length=120)),
        sa.Column("customer", sa.String(length=200)),
        sa.Column("level", sa.String(length=10), nullable=False),
        sa.Column("opened_on", sa.Date(), nullable=False),
        sa.Column("closed_on", sa.Date()),
        sa.Column("reference", sa.String(length=120)),
        sa.Column("note", sa.Text()),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("level IN ('CSI', 'CSII')", name="ck_audit_plan_escalations_level"),
    )
    op.create_index("ix_audit_plan_customer_escalations_plant", "audit_plan_customer_escalations", ["plant"])

    op.create_table(
        "audit_plan_quality_metrics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plant", sa.String(length=80), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("metric", sa.String(length=30), nullable=False),
        sa.Column("value", sa.Numeric(14, 4), nullable=False),
        sa.Column("target", sa.Numeric(14, 4), nullable=False),
        sa.Column("unit", sa.String(length=20)),
        sa.Column("note", sa.Text()),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("plant", "month", "metric", name="uq_audit_plan_quality_metrics"),
        sa.CheckConstraint("metric IN ('nqc', 'scrap')", name="ck_audit_plan_quality_metrics_metric"),
    )
    op.create_index("ix_audit_plan_quality_metrics_plant", "audit_plan_quality_metrics", ["plant"])

    op.create_table(
        "audit_plan_audit_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plant", sa.String(length=80), nullable=False),
        sa.Column("product_line", sa.String(length=120)),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column(
            "support_process_id",
            sa.Integer(),
            sa.ForeignKey("audit_plan_support_processes.id", ondelete="SET NULL"),
        ),
        sa.Column("audited_on", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column(
            "plan_item_id",
            sa.Integer(),
            sa.ForeignKey("audit_plan_items.id", ondelete="SET NULL"),
            unique=True,
        ),
        sa.Column("note", sa.Text()),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_plan_audit_history_plant", "audit_plan_audit_history", ["plant"])
    op.create_index("ix_audit_plan_audit_history_audited_on", "audit_plan_audit_history", ["audited_on"])


def downgrade() -> None:
    op.drop_table("audit_plan_audit_history")
    op.drop_table("audit_plan_quality_metrics")
    op.drop_table("audit_plan_customer_escalations")
    op.drop_table("audit_plan_items")
    op.drop_index("uq_audit_plan_runs_approved_month", table_name="audit_plan_runs")
    op.drop_table("audit_plan_runs")
    op.drop_table("audit_plan_support_processes")
