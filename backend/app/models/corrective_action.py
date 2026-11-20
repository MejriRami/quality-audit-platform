from sqlalchemy import Column, Integer, String, Text, Date, Boolean, TIMESTAMP, ForeignKey
from sqlalchemy.orm import relationship
from app.config.database import Base
from app.models.enums import ca_status_enum

ACTION_TYPE_CORRECTIVE = "corrective"
ACTION_TYPE_IMMEDIATE = "immediate"


class CorrectiveAction(Base):
    __tablename__ = "corrective_actions"

    id = Column(Integer, primary_key=True)
    finding = Column(Text)
    # Migrated CARs have no linked Question (no audit_answer_id), so their
    # "Question / Action" column has nothing to show without this - backfilled
    # from the Monday.com board's own "Question" field, distinct from `finding`.
    migrated_question_text = Column(Text)
    implemented_solution = Column(Text)
    root_cause=Column(Text)
    audit_id = Column(Integer, ForeignKey("audits.id"))
    audit_answer_id = Column(Integer, ForeignKey("audit_answers.id"))
    # Set when the CAR was raised by a VDA sub-requirement (scored 0/4/6/8)
    # rather than by the parent question itself. Several CARs can then share
    # one audit_answer_id; `finding` carries the requirement's own finding.
    audit_answer_requirement_id = Column(
        Integer, ForeignKey("audit_answer_requirements.id"), nullable=True, index=True
    )
    identifier= Column(String(20), unique=True)

    auditee_id = Column(Integer, ForeignKey("audit_auditees.id"), nullable=True)

    reason_why = Column(Text)
    due_date = Column(Date)
    status = Column(ca_status_enum, default="pending")
    escalated = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP(timezone=True))
    submitted_at = Column(TIMESTAMP(timezone=True))
    due_date_base = Column(Date)
    immediate_action_required = Column(Boolean, default=False)
    submission_due_at = Column(TIMESTAMP(timezone=True), nullable=True)
    closure_due_at = Column(TIMESTAMP(timezone=True), nullable=True)

    reassigned_at = Column(TIMESTAMP(timezone=True), nullable=True)
    reassigned_from_email = Column(String(150), nullable=True)
    reassignment_reason = Column(Text, nullable=True)
    cc_emails = Column(Text, nullable=True)

    # Who actually clicked submit and from where. auditee_id/auditee.email
    # reflect current *assignment*, not who submitted — any invited auditee
    # on the audit can submit any of its CARs (see verify_email_for_car), so
    # this is the only durable record of the real submitter and channel.
    submitted_by_email = Column(String(150), nullable=True)
    submission_channel = Column(String(20), nullable=True)  # "portal" | "form_link"

    # "corrective" (root-cause fix, normal due_date cadence) or "immediate"
    # (containment action, 24h/48h cadence, due_date left NULL — see
    # linked_action). Two rows sharing an audit_answer_id/linked_action_id
    # represent one finding split into its containment and root-cause halves.
    action_type = Column(String(20), nullable=False, default=ACTION_TYPE_CORRECTIVE)
    linked_action_id = Column(Integer, ForeignKey("corrective_actions.id"), nullable=True)

    audit = relationship("Audit", back_populates="corrective_actions")
    answer = relationship("AuditAnswer")
    answer_requirement = relationship("AuditAnswerRequirement")
    auditee = relationship("AuditAuditee", foreign_keys=[auditee_id])
    linked_action = relationship(
        "CorrectiveAction",
        remote_side=[id],
        foreign_keys=[linked_action_id],
        uselist=False,
        post_update=True,
    )

    history = relationship("CorrectiveActionHistory", back_populates="corrective_action")
    escalations = relationship("CarEscalation", back_populates="corrective_action")
