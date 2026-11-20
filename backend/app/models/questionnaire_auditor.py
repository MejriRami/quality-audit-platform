from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from app.config.database import Base


class QuestionnaireAuditor(Base):
    __tablename__ = "questionnaire_auditors"

    questionnaire_id = Column(Integer, ForeignKey("questionnaires.id"), primary_key=True)
    auditor_id = Column(Integer, ForeignKey("users.id"), primary_key=True)

    questionnaire = relationship("Questionnaire", back_populates="auditors")
    auditor = relationship("User")
