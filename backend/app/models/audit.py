from sqlalchemy import Boolean, Column, Integer, TIMESTAMP, String, Numeric, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.config.database import Base
from app.models.enums import audit_status_enum, plant_type_enum


class Audit(Base):
    __tablename__ = "audits"

    id = Column(Integer, primary_key=True)
    audit_number = Column(String(20), unique=True, nullable=False)
    status = Column(audit_status_enum, default="planned")

    planned_start_date = Column(TIMESTAMP, nullable=False)
    planned_end_date = Column(TIMESTAMP, nullable=False)
    actual_start_date = Column(TIMESTAMP)
    actual_end_date = Column(TIMESTAMP)

    plant = Column(plant_type_enum)
    sector = Column(String(50))

    auditor_id = Column(Integer, ForeignKey("users.id"))
    # Optional co-auditor. auditor_id stays the lead auditor (owner of the
    # Outlook event, KPIs, CAR reviews); the second auditor is invited to the
    # event, notified, and can see/fill the audit.
    second_auditor_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    questionnaire_id = Column(Integer, ForeignKey("questionnaires.id"))

    report_url = Column(Text)
    hardware_email = Column(String(150))
    total_score = Column(Numeric(10, 4))

    weak_points = Column(Text)
    strong_points = Column(Text)
    total_score = Column(Numeric(10, 4))
    result_class = Column(String(5), nullable=True)
    include_potential_analysis = Column(Boolean, default=False)
    potential_analysis_result_class = Column(String(5), nullable=True)
    created_at = Column(TIMESTAMP)
    event_created = Column(Boolean, default=False)
    event_id = Column(String(200), nullable=True)
    # report_generated = Column(Boolean, default=False)
    auditor = relationship("User", foreign_keys=[auditor_id])
    second_auditor = relationship("User", foreign_keys=[second_auditor_id])
    questionnaire = relationship("Questionnaire")
    supervisor_email = Column(String(150), nullable=True)
    answers = relationship("AuditAnswer", back_populates="audit")
    corrective_actions = relationship("CorrectiveAction", back_populates="audit")
    reschedules = relationship("AuditRescheduleHistory", back_populates="audit")
    auditees = relationship("AuditAuditee", back_populates="audit", cascade="all, delete-orphan")
    unavailability = relationship(
            "AuditUnavailability",
            back_populates="audit",
            cascade="all, delete-orphan"
        )
    