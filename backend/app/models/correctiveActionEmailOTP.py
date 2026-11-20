from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, ForeignKey
from sqlalchemy.orm import relationship
from app.config.database import Base
from datetime import datetime
class CorrectiveActionEmailOTP(Base):
    __tablename__ = "corrective_actions_email_otps"

    id = Column(Integer, primary_key=True)
    corrective_action_id = Column(Integer, ForeignKey("corrective_actions.id"))
    email = Column(String(150), index=True)
    code = Column(String(6))
    expires_at = Column(TIMESTAMP(timezone=True))
    verified = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP(timezone=True), default=datetime.utcnow)

    corrective_action = relationship("CorrectiveAction")
