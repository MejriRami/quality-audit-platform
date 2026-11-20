from sqlalchemy import Column, ForeignKey, Integer, String, Text, TIMESTAMP
from app.config.database import Base


class AuditorChatbotMessage(Base):
    __tablename__ = "auditor_chatbot_messages"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False)
