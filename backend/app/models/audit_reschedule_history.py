from sqlalchemy import Column, Integer, TIMESTAMP, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.config.database import Base
from app.models.enums import audit_action_enum


class AuditRescheduleHistory(Base):
    __tablename__ = "audit_reschedule_history"

    id = Column(Integer, primary_key=True)
    audit_id = Column(Integer, ForeignKey("audits.id"))
    action_type = Column(audit_action_enum)
    old_date = Column(TIMESTAMP)
    new_date = Column(TIMESTAMP)
    reason = Column(Text)
    changed_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(TIMESTAMP)

    audit = relationship("Audit", back_populates="reschedules")
    changed_by_user = relationship("User")
