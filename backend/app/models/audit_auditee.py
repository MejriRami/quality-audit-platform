from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from app.config.database import Base

class AuditAuditee(Base):
    __tablename__ = "audit_auditees"

    id = Column(Integer, primary_key=True, index=True)
    audit_id = Column(Integer, ForeignKey("audits.id", ondelete="CASCADE"))
    email = Column(String(150), nullable=False)

    # Optional link to the local Northwind directory mirror (org_directory_members).
    # NULL for historical rows created before this existed, and for auditees
    # typed manually because they're not in the directory (most people
    # aren't - only a fraction of active Northwind staff have an email on file).
    # `email` stays the source of truth either way; this is purely an
    # enrichment/identity link, never required for the app to function.
    people_id = Column(
        Integer, ForeignKey("org_directory_members.people_id"), nullable=True
    )

    audit = relationship("Audit", back_populates="auditees")
    directory_member = relationship("OrgDirectoryMember")
