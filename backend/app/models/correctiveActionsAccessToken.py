
from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, ForeignKey
from sqlalchemy.orm import relationship
from app.config.database import Base
class CorrectiveActionAccessToken(Base):
    __tablename__ = "corrective_actions_access_tokens"

    id = Column(Integer, primary_key=True)
    corrective_action_id = Column(Integer, ForeignKey("corrective_actions.id"))
    token = Column(String(255), unique=True, index=True)
    expires_at = Column(TIMESTAMP(timezone=True))
    used = Column(Boolean, default=False)

    corrective_action = relationship("CorrectiveAction")