from datetime import datetime

from sqlalchemy import Boolean, Column, Integer, String, TIMESTAMP

from app.config.database import Base


class AuditeePortalEmailOTP(Base):
    __tablename__ = "auditee_portal_email_otps"

    id = Column(Integer, primary_key=True)
    plant = Column(String(100), nullable=False, index=True)
    email = Column(String(150), nullable=False, index=True)
    access_mode = Column(String(20), nullable=False, index=True, default="auditee")
    code = Column(String(6), nullable=False)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False)
    verified = Column(Boolean, default=False, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow, nullable=False)
