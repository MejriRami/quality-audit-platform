from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, Boolean, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.config.database import Base
from datetime import datetime

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    link = Column(String(255), nullable=True)
    read = Column(Boolean, default=False, nullable=False)
    created_at = Column(TIMESTAMP, default=datetime.now, nullable=False)
    meta_data = Column(Text, nullable=True) 
    
    user = relationship("User", foreign_keys=[user_id])
    
    __table_args__ = (
        Index('idx_notification_user_read', 'user_id', 'read'),
        Index('idx_notification_user_created', 'user_id', 'created_at'),
    )