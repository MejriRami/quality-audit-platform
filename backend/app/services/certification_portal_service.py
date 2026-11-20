"""Public access to External Certifications, like the auditee portal: no app
account, an Northwind email verified by a one-time code instead.

- Anyone with an @northwind.com mailbox can view.
- Editing follows the person's role in the Northwind directory (quality managers,
  quality engineers, group quality auditors, group quality), or their app
  roles when they also have an app account.

Codes and sessions reuse the auditee portal tables under their own
plant/access_mode keys, so the two portals never see each other's sessions.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.auditeePortalEmailOTP import AuditeePortalEmailOTP
from app.models.org_directory_member import OrgDirectoryMember
from app.models.portalAccessSession import PortalAccessSession
from app.models.user import User
from app.models.user_role import UserRole
from app.services.email_delivery_service import send_email_sync_tracked
from app.services.role_access_service import can_edit_external_certifications

logger = logging.getLogger(__name__)

PORTAL_KEY = "certifications"       # stored in the shared tables' `plant`
ACCESS_MODE = "certification"
CODE_TTL_MINUTES = 10
SESSION_TTL_HOURS = 12

# Northwind directory roles (org_directory_members.role_name, lowercased) that may
# add or modify certifications.
EDITOR_DIRECTORY_ROLES = {
    "quality manager",
    "quality engineers",
    "group quality auditor",
    "group quality",
}


@dataclass(frozen=True)
class CertificationActor:
    email: str
    can_edit: bool


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _normalize_email(email: str) -> str:
    normalized = (email or "").strip().lower()
    if not normalized.endswith("@northwind.com") or " " in normalized:
        raise HTTPException(status_code=400, detail="Please use your @northwind.com email address.")
    return normalized


def can_edit_email(db: Session, email: str) -> bool:
    email = (email or "").strip().lower()
    member = (
        db.query(OrgDirectoryMember.role_name)
        .filter(func.lower(OrgDirectoryMember.email) == email, OrgDirectoryMember.is_active.is_(True))
        .first()
    )
    if member and (member.role_name or "").strip().lower() in EDITOR_DIRECTORY_ROLES:
        return True
    user = (
        db.query(User)
        .options(joinedload(User.roles).joinedload(UserRole.role))
        .filter(func.lower(User.email) == email)
        .first()
    )
    return bool(user and can_edit_external_certifications(user))


def actor_for_user(db: Session, user: User) -> CertificationActor:
    return CertificationActor(
        email=user.email,
        can_edit=can_edit_external_certifications(user) or can_edit_email(db, user.email),
    )


def request_code(db: Session, email: str) -> dict:
    email = _normalize_email(email)
    now = _now()
    # Only the latest code is valid.
    db.query(AuditeePortalEmailOTP).filter(
        AuditeePortalEmailOTP.plant == PORTAL_KEY,
        AuditeePortalEmailOTP.email == email,
        AuditeePortalEmailOTP.access_mode == ACCESS_MODE,
        AuditeePortalEmailOTP.verified.is_(False),
    ).update({"expires_at": now}, synchronize_session=False)

    code = f"{secrets.randbelow(900_000) + 100_000}"
    db.add(
        AuditeePortalEmailOTP(
            plant=PORTAL_KEY,
            email=email,
            access_mode=ACCESS_MODE,
            code=code,
            verified=False,
            expires_at=now + timedelta(minutes=CODE_TTL_MINUTES),
            created_at=now,
        )
    )
    db.commit()

    sent = send_email_sync_tracked(
        subject="Verification Code - Northwind External Certifications",
        recipients=[email],
        db=db,
        context="certification_portal_otp",
        body_html=f"""
        <html><body style="font-family:Arial,sans-serif;padding:20px;">
          <h2 style="color:#064273;">Northwind External Certifications</h2>
          <p>Your verification code is:</p>
          <p style="font-size:32px;font-weight:bold;letter-spacing:5px;color:#1976D2;">{code}</p>
          <p style="color:#666;">This code expires in {CODE_TTL_MINUTES} minutes.</p>
        </body></html>
        """,
    )
    if not sent:
        raise HTTPException(status_code=502, detail="The verification email could not be sent. Please retry.")
    return {"message": "Verification code sent", "email": email}


def verify_code(db: Session, email: str, code: str) -> dict:
    email = _normalize_email(email)
    otp = (
        db.query(AuditeePortalEmailOTP)
        .filter_by(plant=PORTAL_KEY, email=email, access_mode=ACCESS_MODE, code=(code or "").strip())
        .order_by(AuditeePortalEmailOTP.expires_at.desc())
        .first()
    )
    if not otp or otp.verified:
        raise HTTPException(status_code=401, detail="Invalid verification code.")
    if _aware(otp.expires_at) < _now():
        raise HTTPException(status_code=410, detail="This code has expired. Please request a new one.")

    otp.verified = True
    db.query(PortalAccessSession).filter_by(plant=PORTAL_KEY, email=email, access_mode=ACCESS_MODE).delete()
    now = _now()
    session = PortalAccessSession(
        plant=PORTAL_KEY,
        email=email,
        access_mode=ACCESS_MODE,
        session_token=secrets.token_urlsafe(48),
        expires_at=now + timedelta(hours=SESSION_TTL_HOURS),
        created_at=now,
        last_used_at=now,
    )
    db.add(session)
    db.commit()
    return {
        "session_token": session.session_token,
        "session_expires_at": session.expires_at.isoformat(),
        "email": email,
        "can_edit": can_edit_email(db, email),
    }


def actor_from_session(db: Session, token: str) -> CertificationActor:
    session = (
        db.query(PortalAccessSession)
        .filter_by(session_token=(token or "").strip(), plant=PORTAL_KEY, access_mode=ACCESS_MODE)
        .first()
    )
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session. Please verify your email again.")
    if _aware(session.expires_at) < _now():
        db.delete(session)
        db.commit()
        raise HTTPException(status_code=401, detail="Session expired. Please verify your email again.")
    session.last_used_at = _now()
    db.commit()
    return CertificationActor(email=session.email, can_edit=can_edit_email(db, session.email))
