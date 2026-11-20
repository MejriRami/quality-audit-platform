from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from app.config.database import Base


class QuestionnaireQuestion(Base):
    __tablename__ = "questionnaire_questions"

    questionnaire_id = Column(Integer, ForeignKey("questionnaires.id"), primary_key=True)
    question_id = Column(Integer, ForeignKey("questions.id"), primary_key=True)

    questionnaire = relationship("Questionnaire", back_populates="questions")
    question = relationship("Question")
