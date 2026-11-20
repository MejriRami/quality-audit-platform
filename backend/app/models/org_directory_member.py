from sqlalchemy import Boolean, Column, Integer, String, TIMESTAMP
from app.config.database import Base


class OrgDirectoryMember(Base):
    """Local mirror of the Northwind Central MCP people directory.

    Populated by the nightly sync job (app/services/org_member_directory.py),
    never by user-facing request handlers — reads (pickers, FK lookups from
    audit_auditees.people_id) always go through this table so they never
    depend on the MCP's live availability.

    `people_id` is Northwind's own id from the directory, used as-is as the primary
    key (not a local autoincrement) so the mapping stays 1:1 and trivial to
    reason about.
    """

    __tablename__ = "org_directory_members"

    people_id = Column(Integer, primary_key=True)
    email = Column(String(150), nullable=False, unique=True, index=True)
    full_name = Column(String(200), nullable=False)
    work_unit_name = Column(String(150), nullable=True)
    role_name = Column(String(150), nullable=True)

    # Soft-delete flag: a person who disappears from a live directory pull
    # is marked inactive, never hard-deleted — audit_auditees.people_id rows
    # pointing at them must keep resolving, and "no longer active at Northwind" is
    # itself useful information for a compliance-oriented app.
    is_active = Column(Boolean, nullable=False, default=True)

    last_synced_at = Column(TIMESTAMP(timezone=True), nullable=True)
