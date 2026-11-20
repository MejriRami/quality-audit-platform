"""Local mirror of the Northwind Central MCP people directory.

Design recap (see CHATBOT_ASSISTANT_ARCHITECTURE.md-style docs in the
suppliers-management repo for the MCP itself):

- `org_directory_members` (app/models/org_directory_member.py) is the actual
  backing store for everything that reads the directory in this app -
  pickers, FK lookups from audit_auditees.people_id, etc. Nothing user-facing
  ever calls the MCP live; only `sync_avo_directory()` below does, on a
  schedule, so a slow/unreachable MCP never blocks a request.
- `org_directory_sync_status` (app/models/org_directory_sync_status.py) is a
  singleton row tracking sync health, used to alert an admin once per
  failing streak (not once per failed run) - same dedup shape as
  CarEscalation, generalized to one ongoing job instead of per-CAR events.
- Departed employees are soft-deleted (is_active=False), never hard-deleted,
  so historical audit_auditees.people_id links keep resolving.

Nothing in this module is wired into a scheduler or router yet - that's
app/services/car_reminder_scheduler.py (job wiring) and a future admin
endpoint (manual "sync now" + directory listing for the picker).
"""

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.config.database import SessionLocal
from app.models.org_directory_member import OrgDirectoryMember
from app.models.org_directory_sync_status import OrgDirectorySyncStatus
from app.services.email_delivery_service import send_email_sync_tracked

logger = logging.getLogger(__name__)

ORG_MCP_URL = os.getenv(
    "ORG_MCP_URL", "https://your-app.azurewebsites.net/mcp"
)
ORG_DIRECTORY_ALERT_EMAIL = os.getenv(
    "ORG_DIRECTORY_ALERT_EMAIL", "noel.rossi@example.com"
)
SMTP_FROM_EMAIL = os.getenv("SMTP_USER")

MAX_SYNC_RETRIES = int(os.getenv("ORG_DIRECTORY_SYNC_MAX_RETRIES", "3"))
SYNC_RETRY_DELAY_SECONDS = 5

# Alert once a failing streak reaches this many consecutive failed runs
# (with the nightly schedule this job is meant to run on, 2 == "hasn't
# synced successfully in ~2 days").
ALERT_AFTER_CONSECUTIVE_FAILURES = 2


# ─────────────────────────────────────────────────────────────
# MCP client (adapted from suppliers-management's org_mcp_client.py —
# see docs/org-mcp-integration.md there for the full write-up / gotchas)
# ─────────────────────────────────────────────────────────────


async def _call_mcp_tool(
    tool_name: str,
    arguments: dict,
    *,
    mcp_url: str = ORG_MCP_URL,
    timeout: float = 15.0,
) -> dict:
    """Call a tool on the Northwind Central MCP and return its parsed JSON
    payload. Raises RuntimeError on a {"success": false} response, ValueError
    if the response wasn't valid JSON, and asyncio.TimeoutError if it took
    too long. Imports `mcp` lazily so this module is importable even in
    environments where that dependency isn't installed.
    """
    import asyncio
    import json

    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async def _call() -> dict:
        async with streamable_http_client(mcp_url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                text = next(
                    (b.text for b in result.content if getattr(b, "text", None)),
                    None,
                )
                if not text:
                    raise RuntimeError(f"Empty response from MCP tool '{tool_name}'.")
                payload = json.loads(text)
                if not payload.get("success"):
                    raise RuntimeError(
                        payload.get("error") or f"MCP tool '{tool_name}' failed."
                    )
                return payload

    return await asyncio.wait_for(_call(), timeout=timeout)


async def _fetch_active_members_with_email(
    *, page_size: int = 500, max_pages: int = 20
) -> list[dict]:
    """Paginate `list_members(people_status="Active")` and return only
    people who have an email on file. Returns:
        [{"people_id": int, "full_name": str, "email": str,
          "work_unit_name": str | None, "role_name": str | None}, ...]
    deduped by email. max_pages is a safety cap, same as upstream.
    """
    entries: list[dict] = []
    seen_emails: set[str] = set()
    offset = 0

    for _ in range(max_pages):
        payload = await _call_mcp_tool(
            "list_members",
            {"people_status": "Active", "limit": page_size, "offset": offset},
        )
        rows = payload.get("data") or []
        for row in rows:
            email = (row.get("email") or "").strip().lower()
            if not email or email in seen_emails:
                continue
            seen_emails.add(email)
            assignments = row.get("assignments") or []
            primary = (
                next((a for a in assignments if a.get("is_primary")), assignments[0])
                if assignments
                else None
            )
            entries.append(
                {
                    "people_id": row.get("people_id"),
                    "full_name": (
                        " ".join(
                            p
                            for p in [row.get("first_name"), row.get("last_name")]
                            if p
                        )
                        or email
                    ),
                    "email": email,
                    "work_unit_name": row.get("work_unit_name"),
                    "role_name": primary.get("role_name") if primary else None,
                }
            )
        if len(rows) < page_size:
            break
        offset += page_size

    return entries


# ─────────────────────────────────────────────────────────────
# Local mirror: read paths (never touch the MCP)
# ─────────────────────────────────────────────────────────────


def list_directory_members(
    db: Session, *, include_inactive: bool = False
) -> list[OrgDirectoryMember]:
    """The only thing pickers/endpoints should call - always reads the local
    mirror table, never the live MCP."""
    query = db.query(OrgDirectoryMember)
    if not include_inactive:
        query = query.filter(OrgDirectoryMember.is_active.is_(True))
    return query.order_by(OrgDirectoryMember.full_name).all()


# Audit.plant -> Northwind directory work_unit_name aliases, for plants whose
# name in this app's audits doesn't literally match Northwind's HR unit name.
# Reconciled by hand against a real DB dump on 2026-08-20:
#   - "frankfort" is a typo for Northwind's "Frankfurt".
#   - "monterrey"/"rayones"/"galeana" are three Mexican audit plants that
#     Northwind's HR directory only tracks as one combined "Mexico" work unit -
#     confirmed intentional: one Plant/Quality manager covers all three
#     until Northwind's HR data is split further.
# "medina"/"poitiers"/"anhui" have no entry under any name today (not
# aliased here - they fall through to PLANT_MANAGER_EMAILS in car_service.py
# until Northwind's directory actually covers them).
PLANT_NAME_ALIASES: dict[str, str] = {
    "frankfort": "frankfurt",
    "monterrey": "mexico",
    "rayones": "mexico",
    "galeana": "mexico",
}


def _find_role_holder_email(db: Session, *, role_name: str, plant: str) -> Optional[str]:
    """Email of the active Northwind directory member holding `role_name` for
    `plant` (matched against work_unit_name, case/whitespace-insensitive,
    with PLANT_NAME_ALIASES applied first for known naming mismatches).

    role_name is matched exactly against the directory's own role_name value
    (e.g. "Plant manager", "Quality manager") - each plant has at most one
    holder of either role today (confirmed: one row per role+work_unit_name
    pair), so the first match is returned as-is. Reads only the local
    mirror, same reliability contract as list_directory_members().
    """
    normalized_plant = (plant or "").strip().lower()
    if not normalized_plant:
        return None
    normalized_plant = PLANT_NAME_ALIASES.get(normalized_plant, normalized_plant)
    member = (
        db.query(OrgDirectoryMember)
        .filter(
            OrgDirectoryMember.is_active.is_(True),
            func.lower(OrgDirectoryMember.role_name) == role_name.strip().lower(),
            func.lower(func.trim(OrgDirectoryMember.work_unit_name)) == normalized_plant,
        )
        .first()
    )
    return member.email if member else None


def get_plant_manager_email(db: Session, plant: str) -> Optional[str]:
    """The Northwind directory's 'Plant manager' for `plant`, or None if nobody in
    the synced directory holds that role for this plant (spelling mismatch
    between Audit.plant and Northwind's work_unit_name, or genuinely unassigned)."""
    return _find_role_holder_email(db, role_name="Plant manager", plant=plant)


# Directory role names that count as management for the manager portal: every
# "... manager" (Plant, Quality, Maintenance, HR, Group Purchasing, ...), every
# director, VPs and the CEO - decided 2026-09-29 so managers of any department
# can follow their plant's non-conformities, not only the Plant/Quality manager.
MANAGEMENT_ROLE_PATTERNS = ("%manager%", "%director%", "vp %", "ceo")


def is_plant_management_member(db: Session, *, email: str, plant: str) -> bool:
    """True when `email` is an active directory member with a management role
    (see MANAGEMENT_ROLE_PATTERNS) whose work unit is `plant`."""
    normalized_email = (email or "").strip().lower()
    normalized_plant = (plant or "").strip().lower()
    if not normalized_email or not normalized_plant:
        return False
    normalized_plant = PLANT_NAME_ALIASES.get(normalized_plant, normalized_plant)
    role = func.lower(func.trim(OrgDirectoryMember.role_name))
    return (
        db.query(OrgDirectoryMember)
        .filter(
            OrgDirectoryMember.is_active.is_(True),
            func.lower(OrgDirectoryMember.email) == normalized_email,
            func.lower(func.trim(OrgDirectoryMember.work_unit_name)) == normalized_plant,
            or_(*(role.like(p) for p in MANAGEMENT_ROLE_PATTERNS)),
        )
        .first()
        is not None
    )


def get_quality_manager_email(db: Session, plant: str) -> Optional[str]:
    """The Northwind directory's 'Quality manager' for `plant` - this role is
    per-plant in Northwind's org chart (confirmed: one Quality manager per plant),
    not a single global role. None if nobody in the synced directory holds
    it for this plant."""
    return _find_role_holder_email(db, role_name="Quality manager", plant=plant)


def _get_or_create_status_row(db: Session) -> OrgDirectorySyncStatus:
    status = (
        db.query(OrgDirectorySyncStatus).filter(OrgDirectorySyncStatus.id == 1).first()
    )
    if not status:
        status = OrgDirectorySyncStatus(id=1, consecutive_failures=0)
        db.add(status)
        db.flush()
    return status


# ─────────────────────────────────────────────────────────────
# Sync job (writes the local mirror; the only thing that talks to the MCP)
# ─────────────────────────────────────────────────────────────


def _upsert_members(db: Session, members: list[dict]) -> tuple[int, int]:
    """Upsert by people_id, soft-delete anyone missing from this pull.
    Returns (upserted_count, deactivated_count)."""
    now = datetime.now(timezone.utc)
    seen_ids: set[int] = set()

    upserted = 0
    for m in members:
        people_id = m.get("people_id")
        if people_id is None:
            continue
        seen_ids.add(people_id)
        row = (
            db.query(OrgDirectoryMember)
            .filter(OrgDirectoryMember.people_id == people_id)
            .first()
        )
        if row is None:
            row = OrgDirectoryMember(people_id=people_id)
            db.add(row)
        row.email = m["email"]
        row.full_name = m["full_name"]
        row.work_unit_name = m.get("work_unit_name")
        row.role_name = m.get("role_name")
        row.is_active = True
        row.last_synced_at = now
        upserted += 1

    deactivated = 0
    if seen_ids:
        stale = (
            db.query(OrgDirectoryMember)
            .filter(
                OrgDirectoryMember.is_active.is_(True),
                ~OrgDirectoryMember.people_id.in_(seen_ids),
            )
            .all()
        )
        for row in stale:
            row.is_active = False
            row.last_synced_at = now
            deactivated += 1

    return upserted, deactivated


def _mark_sync_attempt(db: Session, status: OrgDirectorySyncStatus) -> None:
    status.last_attempt_at = datetime.now(timezone.utc)


def _mark_sync_success(db: Session, status: OrgDirectorySyncStatus) -> None:
    status.last_success_at = datetime.now(timezone.utc)
    status.consecutive_failures = 0
    status.last_error = None
    status.alerted_at = None  # reset - the next failing streak can alert again


def _mark_sync_failure(db: Session, status: OrgDirectorySyncStatus, error: str) -> None:
    status.consecutive_failures = (status.consecutive_failures or 0) + 1
    status.last_error = error[:2000]


def _maybe_send_alert(db: Session, status: OrgDirectorySyncStatus) -> bool:
    """Send one alert per failing streak, not one per failed run."""
    if status.consecutive_failures < ALERT_AFTER_CONSECUTIVE_FAILURES:
        return False
    if status.alerted_at is not None:
        return False  # already alerted for this streak
    if not ORG_DIRECTORY_ALERT_EMAIL:
        logger.warning(
            "Northwind directory sync has failed %s times in a row but "
            "ORG_DIRECTORY_ALERT_EMAIL is not configured - no alert sent. "
            "Last error: %s",
            status.consecutive_failures,
            status.last_error,
        )
        return False

    try:
        send_email_sync_tracked(
            subject="⚠️ Northwind directory sync failing",
            recipients=[ORG_DIRECTORY_ALERT_EMAIL],
            body_html=(
                f"<p>The Northwind directory sync job has failed "
                f"<strong>{status.consecutive_failures}</strong> times in a row.</p>"
                f"<p>Last success: {status.last_success_at or 'never'}</p>"
                f"<p>Last error: {status.last_error or 'N/A'}</p>"
                f"<p>The local directory (org_directory_members) is stale but "
                f"still in use - nothing is broken, but new hires/leavers "
                f"won't be reflected in the auditee picker until this is "
                f"fixed. Trigger a manual re-sync once the underlying issue "
                f"is resolved.</p>"
            ),
            db=db,
            context="org_directory_sync_alert",
            sender_email=SMTP_FROM_EMAIL,
            sender_name="Northwind",
        )
    except Exception:
        logger.error("Failed to send Northwind directory sync alert email", exc_info=True)
        return False

    status.alerted_at = datetime.now(timezone.utc)
    return True


def sync_avo_directory(db: Optional[Session] = None) -> dict[str, Any]:
    """Fetch the live directory (with retries) and upsert it into the local
    mirror. On repeated failure, the local table is left untouched - stale
    but correct beats partially wiped - and an admin gets alerted once per
    failing streak. Safe to call from a scheduler or a manual "sync now"
    endpoint; owns its own DB session if one isn't passed in.
    """
    import asyncio

    owns_session = db is None
    db = db or SessionLocal()
    start = time.time()
    summary: dict[str, Any] = {
        "success": False,
        "fetched": 0,
        "upserted": 0,
        "deactivated": 0,
    }

    try:
        status = _get_or_create_status_row(db)
        _mark_sync_attempt(db, status)
        db.commit()

        last_error: Optional[Exception] = None
        members: Optional[list[dict]] = None
        for attempt in range(1, MAX_SYNC_RETRIES + 1):
            try:
                members = asyncio.run(_fetch_active_members_with_email())
                last_error = None
                break
            except Exception as e:
                last_error = e
                logger.warning(
                    "Northwind directory fetch attempt %s/%s failed: %s",
                    attempt,
                    MAX_SYNC_RETRIES,
                    e,
                )
                if attempt < MAX_SYNC_RETRIES:
                    time.sleep(SYNC_RETRY_DELAY_SECONDS)

        status = _get_or_create_status_row(db)
        if last_error is not None or members is None:
            _mark_sync_failure(db, status, str(last_error))
            alerted = _maybe_send_alert(db, status)
            db.commit()
            summary["error"] = str(last_error)
            summary["consecutive_failures"] = status.consecutive_failures
            summary["alert_sent"] = alerted
            logger.error(
                "❌ Northwind directory sync failed after %s attempt(s): %s",
                MAX_SYNC_RETRIES,
                last_error,
            )
            return summary

        summary["fetched"] = len(members)
        upserted, deactivated = _upsert_members(db, members)
        summary["upserted"] = upserted
        summary["deactivated"] = deactivated
        _mark_sync_success(db, status)
        db.commit()
        summary["success"] = True
        logger.info(
            "✅ Northwind directory sync completed - fetched=%s upserted=%s deactivated=%s",
            summary["fetched"],
            upserted,
            deactivated,
        )
        return summary
    finally:
        summary["elapsed_seconds"] = round(time.time() - start, 2)
        if owns_session:
            db.close()
