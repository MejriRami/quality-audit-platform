from sqlalchemy import Column, Integer, String, TIMESTAMP, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from app.config.database import Base

class AuditUnavailabilityAccessToken(Base):
    __tablename__ = "audit_unavailability_access_tokens"

    id = Column(Integer, primary_key=True)
    audit_id = Column(Integer, ForeignKey("audits.id"), nullable=False)
    unavailability_id = Column(Integer, ForeignKey("audit_unavailability.id"), nullable=True, index=True)
    email = Column(String(150), index=True, nullable=False)
    token = Column(String(64), unique=True, index=True, nullable=False)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)

    audit = relationship("Audit")
