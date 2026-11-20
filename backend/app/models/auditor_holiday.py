from sqlalchemy import Column, Integer, String, Date, TIMESTAMP, ForeignKey, func
from sqlalchemy.orm import relationship
from app.config.database import Base


class AuditorHoliday(Base):
    __tablename__ = "auditor_holidays"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    reason = Column(String(255), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

    user = relationship("User")
