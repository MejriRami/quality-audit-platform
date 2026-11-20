from sqlalchemy import Column, Integer, String
from app.config.database import Base


class AuditType(Base):
    __tablename__ = "audit_types"

    id = Column(Integer, primary_key=True)
    value = Column(String(255), unique=True, nullable=False)
