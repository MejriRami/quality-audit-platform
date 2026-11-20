from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.config.database import Base


class QuestionRequirement(Base):
    __tablename__ = "question_requirements"

    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False, index=True)
    requirement_code = Column(String(100))
    description = Column(Text, nullable=False)
    sort_order = Column(Integer)

    question = relationship("Question", back_populates="requirements")
    audit_answer_requirements = relationship(
        "AuditAnswerRequirement",
        back_populates="question_requirement",
    )
