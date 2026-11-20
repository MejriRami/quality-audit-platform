from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.config.database import Base


class Framework(Base):
    __tablename__ = "frameworks"

    id = Column(Integer, primary_key=True)
    code = Column(String(50), nullable=False)
    label = Column(String(150), nullable=False)

    questionnaires = relationship("Questionnaire", back_populates="framework")
