"""Tables for the monthly audit-planning engine (app/services/audit_planning).

- audit_plan_runs / audit_plan_items   one draft/approved plan per month
- audit_plan_customer_escalations      manual input: open CSI / CSII (P2, P3)
- audit_plan_quality_metrics           manual input: monthly NQC / scrap (P11)
- audit_plan_audit_history             completed audits that feed the
                                       "audited in the last N months" checks
                                       (written when a plan item is completed,
                                       or entered by hand for older audits)
- audit_plan_support_processes         the P8 support-process list

`plant` columns hold this app's canonical plant keys (plant_type enum values).
"""

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.config.database import Base


class AuditPlanRun(Base):
    __tablename__ = "audit_plan_runs"

    id = Column(Integer, primary_key=True)
    plan_month = Column(Date, nullable=False, index=True)  # first day of month
    status = Column(String(20), nullable=False, default="draft")  # draft|approved|superseded
    as_of = Column(Date, nullable=False)
    check_status = Column(JSONB, nullable=False, default=dict)
    warnings = Column(JSONB, nullable=False, default=list)
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    generated_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    approved_at = Column(DateTime(timezone=True))
    approved_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))

    items = relationship(
        "AuditPlanItem",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="AuditPlanItem.id",
    )


class AuditPlanItem(Base):
    __tablename__ = "audit_plan_items"

    id = Column(Integer, primary_key=True)
    run_id = Column(Integer, ForeignKey("audit_plan_runs.id", ondelete="CASCADE"), nullable=False, index=True)

    plant = Column(String(80), nullable=False, index=True)
    product_line = Column(String(120))
    project_code = Column(String(80))
    support_process_id = Column(Integer, ForeignKey("audit_plan_support_processes.id", ondelete="SET NULL"))

    trigger_codes = Column(JSONB, nullable=False, default=list)  # ["P4", "P5"]
    checklist = Column(String(120), nullable=False)
    history_kind = Column(String(30), nullable=False)
    evidence = Column(JSONB, nullable=False, default=list)
    complaint_volume = Column(Integer, nullable=False, default=0)
    priority = Column(Integer, nullable=False)  # lowest P-number among triggers

    # scheduled | over_capacity | suppressed_recent | removed | completed
    status = Column(String(30), nullable=False)
    status_reason = Column(Text)
    scheduled_date = Column(Date)
    auditor_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))

    auditee_role = Column(String(80), nullable=False)
    auditee_name = Column(String(200))
    auditee_email = Column(String(150))
    auditee_status = Column(String(30), nullable=False)  # resolved | manual_required | overridden
    auditee_note = Column(Text)

    overridden = Column(Boolean, nullable=False, default=False)
    override_note = Column(Text)
    completed_on = Column(Date)
    updated_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    run = relationship("AuditPlanRun", back_populates="items")
    auditor = relationship("User", foreign_keys=[auditor_user_id])
    support_process = relationship("AuditPlanSupportProcess")


class AuditPlanCustomerEscalation(Base):
    __tablename__ = "audit_plan_customer_escalations"

    id = Column(Integer, primary_key=True)
    plant = Column(String(80), nullable=False, index=True)
    product_line = Column(String(120))
    customer = Column(String(200))
    level = Column(String(10), nullable=False)  # CSI | CSII
    opened_on = Column(Date, nullable=False)
    closed_on = Column(Date)  # NULL = still open
    reference = Column(String(120))
    note = Column(Text)
    updated_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AuditPlanQualityMetric(Base):
    """Monthly NQC / scrap per plant, entered by hand. PPM is read live from
    the roles MCP's KPI results and is not stored here."""

    __tablename__ = "audit_plan_quality_metrics"
    __table_args__ = (
        UniqueConstraint("plant", "month", "metric", name="uq_audit_plan_quality_metrics"),
    )

    id = Column(Integer, primary_key=True)
    plant = Column(String(80), nullable=False, index=True)
    month = Column(Date, nullable=False)  # first day of month
    metric = Column(String(30), nullable=False)  # nqc | scrap
    value = Column(Numeric(14, 4), nullable=False)
    target = Column(Numeric(14, 4), nullable=False)
    unit = Column(String(20))
    note = Column(Text)
    updated_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class AuditPlanAuditHistory(Base):
    __tablename__ = "audit_plan_audit_history"

    id = Column(Integer, primary_key=True)
    plant = Column(String(80), nullable=False, index=True)
    product_line = Column(String(120))
    # line | plant_manager | support_process | recovery_plan | iso14001 | quality_metrics
    kind = Column(String(30), nullable=False)
    support_process_id = Column(Integer, ForeignKey("audit_plan_support_processes.id", ondelete="SET NULL"))
    audited_on = Column(Date, nullable=False, index=True)
    source = Column(String(20), nullable=False)  # plan | manual
    plan_item_id = Column(Integer, ForeignKey("audit_plan_items.id", ondelete="SET NULL"), unique=True)
    note = Column(Text)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AuditPlanSupportProcess(Base):
    __tablename__ = "audit_plan_support_processes"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False, unique=True)
    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)
