from sqlalchemy import Column, Integer, Date, String, ForeignKey, TIMESTAMP
from sqlalchemy.orm import relationship
from app.config.database import Base

class AuditUnavailability(Base):
    __tablename__ = "audit_unavailability"

    id = Column(Integer, primary_key=True)
    audit_id = Column(Integer, ForeignKey("audits.id"), nullable=False)

    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    reason = Column(String(255), nullable=True)
    status = Column(String(20), nullable=False, default="approved")
    requested_by_email = Column(String(150), nullable=True)
    plant_manager_email = Column(String(150), nullable=True)
    decision_by_email = Column(String(150), nullable=True)
    decision_at = Column(TIMESTAMP(timezone=True), nullable=True)
    decision_comment = Column(String(255), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True))

    audit = relationship("Audit", back_populates="unavailability")
