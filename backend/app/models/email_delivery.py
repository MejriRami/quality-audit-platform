from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, Index

from app.config.database import Base


class EmailDelivery(Base):
    __tablename__ = "email_deliveries"

    id = Column(Integer, primary_key=True, index=True)
    subject = Column(String(255), nullable=False)
    recipients = Column(Text, nullable=False)
    cc = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    context = Column(String(100), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=datetime.utcnow)
    last_attempt_at = Column(TIMESTAMP(timezone=True), nullable=True)
    sent_at = Column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_email_deliveries_status_created", "status", "created_at"),
    )

