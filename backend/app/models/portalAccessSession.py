from datetime import datetime

from sqlalchemy import Column, Integer, String, TIMESTAMP

from app.config.database import Base


class PortalAccessSession(Base):
    __tablename__ = "portal_access_sessions"

    id = Column(Integer, primary_key=True)
    plant = Column(String(100), nullable=False, index=True)
    email = Column(String(150), nullable=False, index=True)
    access_mode = Column(String(20), nullable=False, index=True)
    session_token = Column(String(128), nullable=False, unique=True, index=True)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow, nullable=False)
    last_used_at = Column(TIMESTAMP(timezone=True), nullable=True)
