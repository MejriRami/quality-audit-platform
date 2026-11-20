from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, ForeignKey
from sqlalchemy.orm import relationship
from app.config.database import Base


class PortalChatbotMessage(Base):
    __tablename__ = "portal_chatbot_messages"

    id = Column(Integer, primary_key=True)
    plant = Column(String(100), nullable=False)
    email = Column(String(150), nullable=False)
    access_mode = Column(String(20), nullable=False)
    car_id = Column(Integer, ForeignKey("corrective_actions.id"), nullable=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True))

    car = relationship("CorrectiveAction")
