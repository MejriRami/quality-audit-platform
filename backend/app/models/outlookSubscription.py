from sqlalchemy import Column, Integer, String, TIMESTAMP, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class OutlookSubscription(Base):
    __tablename__ = "outlook_subscriptions"
    id = Column(Integer, primary_key=True)
    user_email = Column(String, unique=True, nullable=False)  # organisateur
    subscription_id = Column(String, unique=True, nullable=False)
    expires_at = Column(TIMESTAMP, nullable=False)
