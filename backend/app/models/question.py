from sqlalchemy import Column, ForeignKey, Integer, String, Text, Boolean
from sqlalchemy.orm import relationship
from app.config.database import Base


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True)
    description = Column(Text, nullable=False)
    chapter = Column(String(100))
    weight = Column(Integer)
    critical_value = Column(Integer)
    questionnaire_id = Column(Integer, ForeignKey("questionnaires.id"), nullable=False)

    question_code = Column(String(100))
    element = Column(String(100))
    subgroup = Column(String(100))
    is_asterisk = Column(Boolean, default=False)

    answers = relationship("AuditAnswer", back_populates="question")
    questionnaire = relationship("Questionnaire", back_populates="questions")
    requirements = relationship("QuestionRequirement", back_populates="question")
