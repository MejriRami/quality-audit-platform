from sqlalchemy import Column, Integer, Text, TIMESTAMP
from app.config.database import Base


class OrgDirectorySyncStatus(Base):
    """Singleton status row for the Northwind directory sync job.

    Always exactly one row (id=1). Tracks the last attempt/success and a
    consecutive-failure counter so the sync job can alert an admin once
    (not on every failed run) when the directory has gone stale, and reset
    itself the moment a sync succeeds again — same dedup shape as
    CarEscalation, just for one ongoing job instead of per-CAR events.
    """

    __tablename__ = "org_directory_sync_status"

    id = Column(Integer, primary_key=True, default=1)
    last_attempt_at = Column(TIMESTAMP(timezone=True), nullable=True)
    last_success_at = Column(TIMESTAMP(timezone=True), nullable=True)
    consecutive_failures = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)

    # When an admin was last emailed about a failing streak — cleared back
    # to NULL as soon as a sync succeeds, so the next failing streak can
    # alert again.
    alerted_at = Column(TIMESTAMP(timezone=True), nullable=True)
