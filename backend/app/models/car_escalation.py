from sqlalchemy import Column, Integer, TIMESTAMP, Text, ForeignKey, String
from sqlalchemy.orm import relationship
from app.config.database import Base


class CarEscalation(Base):
    __tablename__ = "car_escalations"

    id = Column(Integer, primary_key=True)
    corrective_action_id = Column(Integer, ForeignKey("corrective_actions.id"))
    escalated_at = Column(TIMESTAMP)

    # ✅ Changed from ForeignKey("users.id") to a plain email string
    # because escalation emails go to auditees, plant managers, and Group VP
    # who are not necessarily in the users table
    email_sent_to = Column(String(150), nullable=True)

    comment = Column(Text)

    corrective_action = relationship("CorrectiveAction", back_populates="escalations")