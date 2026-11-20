from sqlalchemy import Boolean, Column, Integer, String, Text, TIMESTAMP, ForeignKey
from sqlalchemy.orm import relationship
from app.config.database import Base


class PortalChatbotDocument(Base):
    __tablename__ = "portal_chatbot_documents"

    id = Column(Integer, primary_key=True)
    plant = Column(String(100), nullable=False)
    email = Column(String(150), nullable=False)
    access_mode = Column(String(20), nullable=False)
    car_id = Column(Integer, ForeignKey("corrective_actions.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    blob_name = Column(String(500), nullable=False)
    file_url = Column(Text, nullable=False)
    mimetype = Column(String(100), nullable=True)
    size = Column(Integer, nullable=False)
    extracted_text = Column(Text, nullable=False)
    truncated = Column(Boolean, nullable=False, default=False)
    created_at = Column(TIMESTAMP(timezone=True))

    car = relationship("CorrectiveAction")
