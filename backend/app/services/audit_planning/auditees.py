"""Resolve the responsible person (auditee) for a plan item.

Order of preference:
1. P6 items: the project manager recorded on the project itself.
2. The local mirror of the roles MCP (org_directory_members, synced nightly).
3. A live roles-MCP lookup (list_members_by_unit), for people whose role is
   not their primary assignment and so isn't in the mirror.
Anything still unresolved - or a role the MCP doesn't have, like
"Process owner" - is flagged manual_required with the reason.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.org_directory_member import OrgDirectoryMember
from app.services.audit_planning import rules
from app.services.org_member_directory import PLANT_NAME_ALIASES, _call_mcp_tool

logger = logging.getLogger(__name__)

RESOLVED = "resolved"
MANUAL_REQUIRED = "manual_required"
OVERRIDDEN = "overridden"

MCP_ROLES = {"quality engineers", "quality manager", "plant manager", "project manager"}


@dataclass
class Auditee:
    name: Optional[str]
    email: Optional[str]
    status: str
    note: Optional[str] = None


class AuditeeResolver:
    """One instance per plan run - caches lookups so each (plant, role) pair
    hits the MCP at most once."""

    def __init__(self, db: Session):
        self.db = db
        self._cache: dict[tuple[str, str], Auditee] = {}

    def resolve(self, cand: rules.Candidate) -> Auditee:
        role = cand.auditee_role
        if cand.project_manager_email:
            return Auditee(cand.project_manager_name, cand.project_manager_email, RESOLVED, "from project")
        if role.lower() not in MCP_ROLES:
            return Auditee(None, None, MANUAL_REQUIRED, f"'{role}' is not a role in the roles MCP")
        key = (cand.plant, role)
        if key not in self._cache:
            self._cache[key] = self._lookup(cand.plant, role)
        return self._cache[key]

    def _lookup(self, plant: str, role: str) -> Auditee:
        unit = PLANT_NAME_ALIASES.get(plant, plant)
        member = (
            self.db.query(OrgDirectoryMember)
            .filter(
                OrgDirectoryMember.is_active.is_(True),
                func.lower(OrgDirectoryMember.role_name) == role.lower(),
                func.lower(func.trim(OrgDirectoryMember.work_unit_name)) == unit,
            )
            .order_by(OrgDirectoryMember.full_name)
            .first()
        )
        if member:
            return Auditee(member.full_name, member.email, RESOLVED, "roles MCP (directory mirror)")

        try:
            payload = asyncio.run(
                _call_mcp_tool("list_members_by_unit", {"unit_name": unit, "limit": 500})
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("audit planning: MCP lookup failed for %s/%s: %s", plant, role, exc)
            return Auditee(None, None, MANUAL_REQUIRED, f"roles MCP unavailable: {type(exc).__name__}")

        for person in payload.get("data") or []:
            email = (person.get("email") or "").strip().lower()
            roles = {
                (a.get("role_name") or "").strip().lower()
                for a in person.get("assignments") or []
            }
            if email and role.lower() in roles:
                name = " ".join(p for p in [person.get("first_name"), person.get("last_name")] if p)
                return Auditee(name or email, email, RESOLVED, "roles MCP (live)")

        return Auditee(None, None, MANUAL_REQUIRED, f"no active '{role}' found for {plant} in the roles MCP")
