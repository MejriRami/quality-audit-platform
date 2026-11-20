"""Endpoints for the local Northwind directory mirror (org_directory_members).

These are the only sanctioned way for anything client-side to see directory
data - per docs/org-mcp-integration.md's own advice, the MCP itself is never
called directly from a browser (no auth on it, and it exposes write tools).
Reads here always come from the local table (app/services/org_member_directory
.list_directory_members), never a live MCP call, so this endpoint is fast and
available even if the MCP is down.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.models.user import User
from app.services.admin_service import require_admin
from app.services.auth_service import get_current_user
from app.services.org_member_directory import list_directory_members, sync_avo_directory

router = APIRouter(prefix="/org-directory", tags=["Northwind Directory"])


class DirectoryMemberOut(BaseModel):
    people_id: int
    full_name: str
    email: str
    work_unit_name: str | None = None
    role_name: str | None = None

    class Config:
        from_attributes = True


@router.get("/members", response_model=list[DirectoryMemberOut])
def get_directory_members(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Active Northwind employees with an email on file, for the auditee
    picker's type-to-filter list. Manual entry stays available client-side
    for anyone not found here - most Northwind staff don't have an email in this
    directory (factory floor roles, etc.)."""
    return list_directory_members(db)


@router.post("/sync")
def trigger_directory_sync(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manual re-sync, for right after a known bulk HR change instead of
    waiting for the nightly job. Same function the scheduler calls; runs
    synchronously and returns its summary. Admin-only - this hits the live
    MCP, unlike GET /members which only ever reads the local mirror."""
    require_admin(current_user)
    return sync_avo_directory(db)
