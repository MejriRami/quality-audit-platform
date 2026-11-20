from sqlalchemy import Column, Integer, String, ForeignKey, TIMESTAMP, Time
from sqlalchemy.orm import relationship
from app.config.database import Base


class Questionnaire(Base):
    __tablename__ = "questionnaires"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False)
    target_duration = Column(Time(timezone=False), nullable=True)
    score_calculation = Column(String(255))
    created_by = Column(Integer, ForeignKey("users.id"))
    status = Column(String(50))
    version = Column(Integer, default=1)
    created_at = Column(TIMESTAMP)

    framework_id = Column(Integer, ForeignKey("frameworks.id"), nullable=False)
    type_id = Column(Integer, ForeignKey("audit_types.id"))
    guideline_id = Column(
    Integer,
    ForeignKey("documents.id", ondelete="SET NULL"),
    nullable=True
)
    potential_analysis_questionnaire_id = Column(
        Integer, ForeignKey("questionnaires.id"), nullable=True
    )

    framework = relationship("Framework", back_populates="questionnaires")
    creator = relationship("User")
    audit_type = relationship("AuditType")
    potential_analysis_questionnaire = relationship(
        "Questionnaire", remote_side=[id]
    )

    auditors = relationship("QuestionnaireAuditor", back_populates="questionnaire", cascade="all, delete-orphan")
    guideline = relationship("Document")
    questions = relationship("Question", back_populates="questionnaire", cascade="all, delete")

