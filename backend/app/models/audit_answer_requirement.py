from sqlalchemy import Boolean, Column, ForeignKey, Integer, Text, Float
from sqlalchemy.orm import relationship

from app.config.database import Base


class AuditAnswerRequirement(Base):
    __tablename__ = "audit_answer_requirements"

    id = Column(Integer, primary_key=True)
    audit_answer_id = Column(Integer, ForeignKey("audit_answers.id"), nullable=False, index=True)
    question_requirement_id = Column(
        Integer,
        ForeignKey("question_requirements.id"),
        nullable=False,
        index=True,
    )
    value = Column(Float)
    fulfilled = Column(Boolean)
    finding_text = Column(Text)
    evidence_json = Column(Text)

    audit_answer = relationship("AuditAnswer", back_populates="requirements")
    question_requirement = relationship(
        "QuestionRequirement",
        back_populates="audit_answer_requirements",
    )
