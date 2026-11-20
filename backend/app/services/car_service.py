"""
car_service.py
==============
All business logic for Corrective Action Reports (CAR).

Responsibilities
----------------
- Token validation
- OTP lifecycle (request / verify)
- Form data retrieval
- File upload via Azure Blob Storage
- Form submission
- Due-date recomputation after unavailability periods
- Helper predicates (is_editable, normalize_status, …)

The router (car_router.py) should be thin: validate HTTP inputs, call a
service function, return the result.
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import secrets
import asyncio
from datetime import datetime, timedelta, timezone, date
from typing import List, Optional, Tuple

from fastapi import HTTPException, UploadFile
from sqlalchemy import String, cast, func
from sqlalchemy.orm import Session, joinedload

from app.models.CarUnavailability import AuditUnavailability
from app.models.audit import Audit
from app.models.audit_answr import AuditAnswer
from app.models.audit_auditee import AuditAuditee
from app.models.auditUnavailabilityAccessToken import AuditUnavailabilityAccessToken
from app.models.auditeePortalEmailOTP import AuditeePortalEmailOTP
from app.models.correctiveActionEmailOTP import CorrectiveActionEmailOTP
from app.models.correctiveActionsAccessToken import CorrectiveActionAccessToken
from app.models.corrective_action import CorrectiveAction, ACTION_TYPE_IMMEDIATE
from app.models.car_escalation import CarEscalation
from app.models.document import Document
from app.models.portalAccessSession import PortalAccessSession
from app.models.question import Question
from app.models.questionnaire import Questionnaire
from app.models.audit_answer_requirement import AuditAnswerRequirement
from app.models.corrective_action_history import CorrectiveActionHistory
from app.models.user import User
from app.models.user_role import UserRole
from app.services import notification_service
from app.services.blob_storage_service import (
    upload_car_document,
    delete_blob,
    _extract_blob_name,
    get_fresh_doc_url
)
from app.services.role_access_service import has_admin_role
from app.services.org_member_directory import (
    get_plant_manager_email,
    get_quality_manager_email,
    is_plant_management_member,
)

from app.utils.due_date import recompute_due_date_from_base
from app.utils.send_car_email import (
    build_auditee_portal_url,
    build_car_email_body,
    build_car_form_url,
    build_unavailability_url,
    get_or_create_car_token,
    send_email,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EDITABLE_STATUSES: frozenset[str] = frozenset({"pending", "rejected"})
LOCKED_STATUSES: frozenset[str] = frozenset({"submitted", "accepted", "closed"})

OTP_TTL_MINUTES = 10          # how long the code itself is valid
SESSION_TTL_MINUTES = 1440    # how long the verified session lasts (24h; can refresh form)
PORTAL_SESSION_TTL_MINUTES = 1440  # 24h
DECISION_BASE_URL = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000")
# Fixed plant -> plant manager emails mapping (backend-owned static source).
# Each plant can have one or more manager emails.
# Update these emails according to your organization directory.
# Fallback to role-based check (admin_or_quality_manager) also applies.
PLANT_MANAGER_EMAILS: dict[str, list[str]] = {
    "atlas": ["noel.rossi@example.com"],
    "frankfort": ["noel.rossi@example.com"],
    "rayones": ["noel.rossi@example.com"],
    "carthage": ["noel.rossi@example.com"],
    "medina": ["noel.rossi@example.com"],
    "daegu": ["noel.rossi@example.com"],
    "monterrey": ["noel.rossi@example.com"],
    "anhui": ["noel.rossi@example.com"],
    "galeana": ["noel.rossi@example.com"],
    "poitiers": ["noel.rossi@example.com"],
    "tianjin": ["noel.rossi@example.com"],
    "kunshan": ["noel.rossi@example.com"],
    "chennai": ["noel.rossi@example.com"],
    "loire": ["noel.rossi@example.com"],
}


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------

def normalize_status(value: str) -> str:
    return str(value).strip().lower()


def is_car_editable(car: CorrectiveAction) -> bool:
    return normalize_status(car.status) in EDITABLE_STATUSES


def is_car_locked(car: CorrectiveAction) -> bool:
    return normalize_status(car.status) in LOCKED_STATUSES


# Auditors may need to reassign a CAR after it's already been submitted — the
# original auditee has left the company being the recurring case — so
# reassignment uses its own, looser rule than the auditee-facing "form is
# locked" check above: "submitted" is reassignable, only "accepted"/"closed"
# (truly finished) are not. The auditee self-service reassign flow keeps the
# stricter is_car_locked rule — an auditee reassigning their own already
# -submitted work without auditor involvement is a different situation.
REASSIGN_BLOCKED_STATUSES: frozenset[str] = frozenset({"accepted", "closed"})


def is_reassignment_blocked(car: CorrectiveAction, initiated_by_auditor: bool) -> bool:
    if initiated_by_auditor:
        return normalize_status(car.status) in REASSIGN_BLOCKED_STATUSES
    return is_car_locked(car)
def utc_now() -> datetime:
    return datetime.now(timezone.utc)
def ensure_aware_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


WHY_LINE_PATTERN = re.compile(r"^\s*(?:why\s*\d+|why)\s*[:\-.)]?\s+.+$", re.IGNORECASE)


def _count_why_lines(root_cause: str) -> int:
    lines = [line.strip() for line in (root_cause or "").splitlines() if line.strip()]
    return sum(1 for line in lines if WHY_LINE_PATTERN.match(line))


def _validate_root_cause_format(root_cause: str) -> None:
    why_count = _count_why_lines(root_cause)
    if why_count < 3:
        raise HTTPException(
            status_code=400,
            detail=(
                "Root cause must use a 5 Whys structure with at least 3 Why statements "
                "(for example: Why 1, Why 2, Why 3)."
            ),
        )

def utc_now_naive() -> datetime:
    """Return current UTC time as timezone-NAIVE datetime (for DB storage)."""
    return datetime.utcnow()


def _normalize_portal_plant(plant: str) -> str:
    return (plant or "").strip().lower()


def _normalize_portal_email(email: str) -> str:
    return (email or "").strip().lower()


def _normalize_access_mode(access_mode: str | None) -> str:
    mode = (access_mode or "auditee").strip().lower()
    if mode not in {"auditee", "manager"}:
        raise HTTPException(status_code=400, detail="access_mode must be either 'auditee' or 'manager'.")
    return mode


def _assert_northwind_email(email: str) -> None:
    normalized_email = _normalize_portal_email(email)
    if not normalized_email.endswith("@northwind.com"):
        raise HTTPException(
            status_code=400,
            detail="Only Northwind email addresses are allowed for the auditee portal.",
        )


def _get_portal_manager_user(email: str, db: Session) -> User | None:
    normalized_email = _normalize_portal_email(email)
    user = (
        db.query(User)
        .options(joinedload(User.roles).joinedload(UserRole.role))
        .filter(func.lower(User.email) == normalized_email)
        .first()
    )
    return user


def _assert_portal_access_allowed(
    *,
    plant: str,
    email: str,
    access_mode: str,
    db: Session,
) -> None:
    normalized_email = _normalize_portal_email(email)
    normalized_plant = _normalize_portal_plant(plant)

    if access_mode == "auditee":
        return

    # Plant manager / quality manager for this specific plant, sourced from
    # the Northwind Central MCP directory (synced nightly into
    # org_directory_members - see app/services/org_member_directory.py).
    # This is the source of truth for both roles; PLANT_MANAGER_EMAILS below
    # is kept only as a manual fallback while the MCP directory's plant
    # naming (work_unit_name) is being reconciled against Audit.plant.
    for lookup in (get_plant_manager_email, get_quality_manager_email):
        directory_email = lookup(db, plant)
        if directory_email and directory_email.strip().lower() == normalized_email:
            return

    # Any other manager or director of this plant (any department) gets the
    # same plant-wide view.
    if is_plant_management_member(db, email=normalized_email, plant=normalized_plant):
        return

    # Manual fallback: static plant -> manager emails mapping, for plants not
    # yet resolving correctly against the Northwind directory.
    mapped_manager_emails = PLANT_MANAGER_EMAILS.get(normalized_plant, [])
    if mapped_manager_emails and normalized_email in [em.strip().lower() for em in mapped_manager_emails]:
        return

    # Fallback: allow access if the app user account itself has an admin role
    # (system admins bypass plant scoping entirely; plain "quality manager"
    # app-role no longer bypasses it - that access is now plant-scoped via
    # the Northwind directory check above).
    user = _get_portal_manager_user(normalized_email, db)
    if user and has_admin_role(user):
        return

    raise HTTPException(
        status_code=403,
        detail="This email is not authorized for manager portal access. Manager access is for managers and directors of this plant in the Northwind directory, or users with an admin role.",
    )


def _create_portal_session(
    *,
    plant: str,
    email: str,
    access_mode: str,
    db: Session,
) -> PortalAccessSession:
    normalized_plant = _normalize_portal_plant(plant)
    normalized_email = _normalize_portal_email(email)
    normalized_mode = _normalize_access_mode(access_mode)
    now = datetime.now(timezone.utc)

    existing_sessions = (
        db.query(PortalAccessSession)
        .filter(
            PortalAccessSession.plant == normalized_plant,
            PortalAccessSession.email == normalized_email,
            PortalAccessSession.access_mode == normalized_mode,
        )
        .all()
    )
    for session in existing_sessions:
        db.delete(session)
    db.flush()

    session = PortalAccessSession(
        plant=normalized_plant,
        email=normalized_email,
        access_mode=normalized_mode,
        session_token=secrets.token_urlsafe(48),
        expires_at=now + timedelta(minutes=PORTAL_SESSION_TTL_MINUTES),
        created_at=now,
        last_used_at=now,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _get_valid_portal_session(
    *,
    plant: str,
    email: str,
    access_mode: str,
    session_token: str,
    db: Session,
) -> PortalAccessSession:
    normalized_plant = _normalize_portal_plant(plant)
    normalized_email = _normalize_portal_email(email)
    normalized_mode = _normalize_access_mode(access_mode)
    token = (session_token or "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing portal session token.")

    session = (
        db.query(PortalAccessSession)
        .filter(
            PortalAccessSession.session_token == token,
            PortalAccessSession.plant == normalized_plant,
            PortalAccessSession.email == normalized_email,
            PortalAccessSession.access_mode == normalized_mode,
        )
        .first()
    )
    if not session:
        raise HTTPException(status_code=401, detail="Invalid portal session.")

    expires_at = ensure_aware_utc(session.expires_at)
    now = datetime.now(timezone.utc)
    if expires_at and expires_at < now:
        db.delete(session)
        db.commit()
        raise HTTPException(status_code=401, detail="Portal session expired. Please verify again.")

    session.last_used_at = now
    db.commit()
    db.refresh(session)
    return session
# ---------------------------------------------------------------------------
# Token / authorization helpers
# ---------------------------------------------------------------------------

def get_car_from_token(token: str, db: Session) -> CorrectiveAction:
    access_token = (
        db.query(CorrectiveActionAccessToken)
        .filter_by(token=token)
        .first()
    )
    if not access_token:
        raise HTTPException(status_code=404, detail="Invalid access link")

    expires_at = ensure_aware_utc(access_token.expires_at)
    if expires_at and expires_at < utc_now():
        raise HTTPException(status_code=410, detail="This access link has expired")

    car = (
        db.query(CorrectiveAction)
        .filter_by(id=access_token.corrective_action_id)
        .first()
    )
    if not car:
        raise HTTPException(status_code=404, detail="Corrective action not found")

    return car


def verify_email_for_car(car: CorrectiveAction, email: str) -> bool:
    """True when *email* matches any auditee assigned to the CAR's audit
    (case-insensitive), not just the CAR's own single owner."""
    normalized_email = (email or "").strip().lower()
    if not normalized_email:
        return False
    audit_auditees = car.audit.auditees if car.audit else []
    return any(
        (auditee.email or "").strip().lower() == normalized_email
        for auditee in audit_auditees
    )


def _assert_email_authorized(car: CorrectiveAction, email: str) -> None:
    if not verify_email_for_car(car, email):
        raise HTTPException(
            status_code=403,
            detail="Email not authorized for this corrective action",
        )


def _query_auditee_portal_cars(
    plant: str,
    email: str,
    access_mode: str,
    db: Session,
    status: str | None = None,
) -> list[CorrectiveAction]:
    normalized_plant = _normalize_portal_plant(plant)
    normalized_email = _normalize_portal_email(email)
    normalized_mode = _normalize_access_mode(access_mode)

    query = (
        db.query(CorrectiveAction)
        .options(
            joinedload(CorrectiveAction.audit).joinedload(Audit.auditees),
            joinedload(CorrectiveAction.audit)
            .joinedload(Audit.questionnaire)
            .joinedload(Questionnaire.framework),
            joinedload(CorrectiveAction.audit)
            .joinedload(Audit.questionnaire)
            .joinedload(Questionnaire.audit_type),
            joinedload(CorrectiveAction.answer)
            .joinedload(AuditAnswer.question)
            .joinedload(Question.requirements),
            # _serialize_related_requirement reads question.questionnaire.framework
            # (standard/checklist name) — eager-load it here too, otherwise each
            # CAR row triggers its own lazy-load query for it.
            joinedload(CorrectiveAction.answer)
            .joinedload(AuditAnswer.question)
            .joinedload(Question.questionnaire)
            .joinedload(Questionnaire.framework),
            joinedload(CorrectiveAction.answer)
            .joinedload(AuditAnswer.requirements)
            .joinedload(AuditAnswerRequirement.question_requirement),
            joinedload(CorrectiveAction.history).joinedload(CorrectiveActionHistory.auditor),
            joinedload(CorrectiveAction.auditee),
        )
        .join(Audit, CorrectiveAction.audit_id == Audit.id)
        .filter(func.lower(cast(Audit.plant, String)) == normalized_plant)
        .order_by(Audit.planned_start_date.desc(), CorrectiveAction.created_at.desc())
    )

    if normalized_mode == "auditee":
        # Any auditee assigned to the audit can see/act on its CARs, not just the
        # single auditee the CAR happens to be owned by (ownership defaults to the
        # first auditee when no per-finding assignment is made).
        query = query.join(AuditAuditee, AuditAuditee.audit_id == Audit.id)
        query = query.filter(func.lower(AuditAuditee.email) == normalized_email)

    if status:
        query = query.filter(func.lower(cast(CorrectiveAction.status, String)) == status.strip().lower())

    return query.all()


# ---------------------------------------------------------------------------
# Rejection history / related-requirement context surfaced to the auditee
# ---------------------------------------------------------------------------

# VDA 6.3 process element structure is fixed/public (mirrors the same table
# used to ground the coaching chatbot's prompt in chatbot_service.py).
VDA_ELEMENT_LABELS = {
    "P1": "P1 - Potential Analysis",
    "P2": "P2 - Project Management",
    "P3": "P3 - Planning of product and process development",
    "P4": "P4 - Realization of product and process development",
    "P5": "P5 - Supplier Management",
    "P6": "P6 - Process Analysis Production",
    "P7": "P7 - Customer Care, Customer Satisfaction, Service",
}


def _serialize_review_history(car: CorrectiveAction) -> list[dict]:
    """Auditor accept/reject decisions for this CAR, oldest first, so the
    auditee can see the full back-and-forth across resubmissions — not just
    the CAR's current status."""
    history = sorted(
        (h for h in (car.history or []) if h.reviewed_at is not None),
        key=lambda h: h.reviewed_at,
    )
    return [
        {
            "decision": h.decision,
            "comment": h.comment,
            "reviewed_at": h.reviewed_at.isoformat() if h.reviewed_at else None,
            "auditor_name": (
                f"{h.auditor.first_name} {h.auditor.last_name}".strip()
                if h.auditor
                else None
            ),
        }
        for h in history
    ]


def _latest_rejection_reason(car: CorrectiveAction) -> Optional[str]:
    """Most recent 'rejected' review comment — distinct from `reason_why`
    (the auditor's original reason for raising the CAR in the first place).
    This is what the auditee actually needs to address before resubmitting."""
    rejections = [
        h for h in (car.history or []) if h.decision == "rejected" and h.reviewed_at
    ]
    if not rejections:
        return None
    return max(rejections, key=lambda h: h.reviewed_at).comment


def _serialize_related_requirement(car: CorrectiveAction) -> dict:
    """The finding's question/clause/process context, so the auditee can see
    exactly what requirement they're being asked to address — not just the
    auditor's free-text finding.

    Different standards structure a "question" differently (VDA 6.3 groups
    questions under P1-P7 process elements; IATF/internal checklists instead
    use a chapter/clause number), so this surfaces whichever of those the
    question actually carries, plus which standard and checklist it came
    from — the auditee otherwise has no way to tell a VDA finding from an
    IATF or internal-audit one.
    """
    answer = car.answer
    question = answer.question if answer else None
    questionnaire = question.questionnaire if question else None
    framework = questionnaire.framework if questionnaire else None
    element_code = (
        (question.element or "").strip().upper() if question and question.element else None
    )

    answer_requirements_by_req_id = {
        r.question_requirement_id: r for r in (answer.requirements if answer else [])
    }
    requirements = []
    if question and question.requirements:
        ordered = sorted(
            question.requirements,
            key=lambda r: (r.sort_order if r.sort_order is not None else 9999, r.id),
        )
        for req in ordered:
            answer_req = answer_requirements_by_req_id.get(req.id)
            requirements.append(
                {
                    "requirement_code": req.requirement_code,
                    "description": req.description,
                    "fulfilled": answer_req.fulfilled if answer_req else None,
                    "value": answer_req.value if answer_req else None,
                    "finding_text": answer_req.finding_text if answer_req else None,
                    # The requirement this CAR was raised for (VDA requirement CARs).
                    "is_car_requirement": bool(
                        answer_req
                        and car.audit_answer_requirement_id is not None
                        and answer_req.id == car.audit_answer_requirement_id
                    ),
                }
            )

    return {
        "standard_code": framework.code if framework else None,
        "standard_label": framework.label if framework else None,
        "questionnaire_name": questionnaire.name if questionnaire else None,
        "question_code": getattr(question, "question_code", None) if question else None,
        "question_description": question.description if question else None,
        "chapter": question.chapter if question and question.chapter else None,
        "subgroup": question.subgroup if question and question.subgroup else None,
        "element": VDA_ELEMENT_LABELS.get(element_code, element_code) if element_code else None,
        "standard_paragraph": answer.standard_paragraph if answer else None,
        "process": answer.process if answer else None,
        "requirements": requirements,
    }


# ---------------------------------------------------------------------------
# OTP – request
# ---------------------------------------------------------------------------

async def request_otp(token: str, email: str, db: Session) -> dict:
    car = get_car_from_token(token, db)
    _assert_email_authorized(car, email)

    # Only fully "already submitted" when the linked action (if any) is also
    # locked -- otherwise a completed corrective section would wrongly block
    # access to a still-pending immediate section behind the same token.
    fully_locked = is_car_locked(car) and (
        car.linked_action is None or is_car_locked(car.linked_action)
    )
    if fully_locked:
        return {
            "message": "This corrective action form has already been submitted",
            "already_submitted": True,
            "submitted_at": (
                car.submitted_at.strftime("%d/%m/%Y %H:%M")
                if car.submitted_at else None
            ),
            "email": email,
        }

    now = datetime.now(timezone.utc)

    db.expire_all()  # ← force fresh DB read

    existing_verified_otp = (
        db.query(CorrectiveActionEmailOTP)
        .filter(
            CorrectiveActionEmailOTP.corrective_action_id == car.id,
            CorrectiveActionEmailOTP.email == email,
            CorrectiveActionEmailOTP.verified == True,
        )
        .order_by(CorrectiveActionEmailOTP.expires_at.desc())
        .first()
    )

    if existing_verified_otp:
        existing_expires = ensure_aware_utc(existing_verified_otp.expires_at)
        
        logger.warning(
            "REQUEST_OTP session check: otp_id=%s expires=%s now=%s valid=%s",
            existing_verified_otp.id,
            existing_expires,
            now,
            existing_expires > now if existing_expires else False,
        )

        if existing_expires and existing_expires > now:
            # Genuinely valid — skip OTP
            return {
                "message": "Email already verified",
                "already_submitted": False,
                "already_verified": True,
                "email": email,
            }
        else:

            existing_verified_otp.verified = False
            db.commit()
            logger.warning(
                "REQUEST_OTP: expired verified session invalidated for otp_id=%s",
                existing_verified_otp.id,
            )

    # Invalidate old unverified codes
    db.query(CorrectiveActionEmailOTP).filter(
        CorrectiveActionEmailOTP.corrective_action_id == car.id,
        CorrectiveActionEmailOTP.email == email,
        CorrectiveActionEmailOTP.verified == False,
    ).update({"expires_at": now}, synchronize_session=False)

    code = f"{random.randint(100_000, 999_999)}"
    otp = CorrectiveActionEmailOTP(
        corrective_action_id=car.id,
        email=email,
        code=code,
        verified=False,
        expires_at=now + timedelta(minutes=OTP_TTL_MINUTES),
        created_at=now,
    )
    db.add(otp)
    db.commit()
    try:
        await  send_email(
            subject="Code de vérification – Northwind",
            recipients=[email],
            db=db,
            context="car_otp",
            body_html=f"""
            <html>
            <body style="font-family:Arial,sans-serif;padding:20px;">
              <div style="max-width:600px;margin:auto;background:white;padding:30px;
                          border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,.1);">
                <h2 style="color:#1B5E20;">Code de vérification – Formulaire Corrective Action</h2>
                <p>Bonjour,</p>
                <p>Votre code de vérification pour accéder au formulaire d'action corrective est :</p>
                <div style="background:#f5f5f5;padding:20px;text-align:center;
                            margin:20px 0;border-radius:4px;">
                  <span style="font-size:32px;font-weight:bold;color:#1976D2;
                               letter-spacing:5px;">{code}</span>
                </div>
                <p style="color:#666;">Ce code expire dans {OTP_TTL_MINUTES} minutes.</p>
                <p style="margin-top:30px;">
                  Cordialement,<br/>
                  <strong>Équipe Qualité – Northwind</strong>
                </p>
              </div>
            </body>
            </html>
            """,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error sending email: {exc}")

    return {
        "message": "OTP code sent successfully to email",
        "already_submitted": False,
        "already_verified": False,
        "email": email,
    }
# ---------------------------------------------------------------------------
# OTP – verify
# ---------------------------------------------------------------------------


async def request_auditee_portal_otp(
    plant: str,
    email: str,
    access_mode: str,
    db: Session,
) -> dict:
    _assert_northwind_email(email)
    normalized_plant = _normalize_portal_plant(plant)
    normalized_email = _normalize_portal_email(email)
    normalized_mode = _normalize_access_mode(access_mode)

    _assert_portal_access_allowed(
        plant=normalized_plant,
        email=normalized_email,
        access_mode=normalized_mode,
        db=db,
    )

    matching_cars = _query_auditee_portal_cars(
        normalized_plant,
        normalized_email,
        normalized_mode,
        db,
    )

    if not matching_cars:
        return {
            "message": "No corrective actions were found for this plant and email.",
            "otp_sent": False,
            "already_verified": False,
            "plant": normalized_plant,
            "email": normalized_email,
            "access_mode": normalized_mode,
        }

    now = datetime.now(timezone.utc)

    existing_session = (
        db.query(PortalAccessSession)
        .filter(
            PortalAccessSession.plant == normalized_plant,
            PortalAccessSession.email == normalized_email,
            PortalAccessSession.access_mode == normalized_mode,
        )
        .order_by(PortalAccessSession.expires_at.desc())
        .first()
    )
    if existing_session:
        expires_at = ensure_aware_utc(existing_session.expires_at)
        if expires_at and expires_at > now:
            existing_session.last_used_at = now
            db.commit()
            db.refresh(existing_session)
            return {
                "message": "Email already verified",
                "otp_sent": False,
                "already_verified": True,
                "plant": normalized_plant,
                "email": normalized_email,
                "access_mode": normalized_mode,
                "session_token": existing_session.session_token,
                "session_expires_at": existing_session.expires_at.isoformat(),
            }
        db.delete(existing_session)
        db.commit()

    db.query(AuditeePortalEmailOTP).filter(
        AuditeePortalEmailOTP.plant == normalized_plant,
        AuditeePortalEmailOTP.email == normalized_email,
        AuditeePortalEmailOTP.access_mode == normalized_mode,
        AuditeePortalEmailOTP.verified == False,
    ).update({"expires_at": now}, synchronize_session=False)

    code = f"{random.randint(100_000, 999_999)}"
    otp = AuditeePortalEmailOTP(
        plant=normalized_plant,
        email=normalized_email,
        access_mode=normalized_mode,
        code=code,
        verified=False,
        expires_at=now + timedelta(minutes=OTP_TTL_MINUTES),
        created_at=now,
    )
    db.add(otp)
    db.commit()

    portal_title = "Manager" if normalized_mode == "manager" else "Auditee"
    try:
        await send_email(
            subject=f"Verification Code - Northwind {portal_title} Portal",
            recipients=[normalized_email],
            db=db,
            context="auditee_portal_otp",
            body_html=f"""
            <html>
            <body style="font-family:Arial,sans-serif;padding:20px;">
              <div style="max-width:600px;margin:auto;background:white;padding:30px;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,.1);">
                <h2 style="color:#1B5E20;">Verification Code - Northwind {portal_title} Portal</h2>
                <p>Hello,</p>
                <p>Your verification code for the {portal_title.lower()} portal is:</p>
                <div style="background:#f5f5f5;padding:20px;text-align:center;margin:20px 0;border-radius:4px;">
                  <span style="font-size:32px;font-weight:bold;color:#1976D2;letter-spacing:5px;">{code}</span>
                </div>
                <p style="color:#666;">This code expires in {OTP_TTL_MINUTES} minutes.</p>
              </div>
            </body>
            </html>
            """,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error sending email: {exc}")

    return {
        "message": "OTP code sent successfully to email",
        "otp_sent": True,
        "already_verified": False,
        "plant": normalized_plant,
        "email": normalized_email,
        "access_mode": normalized_mode,
    }


def verify_otp(token: str, email: str, code: str, db: Session) -> dict:
    car = get_car_from_token(token, db)
    _assert_email_authorized(car, email)

    otp = (
        db.query(CorrectiveActionEmailOTP)
        .filter_by(corrective_action_id=car.id, email=email, code=code)
        .order_by(CorrectiveActionEmailOTP.expires_at.desc())
        .first()
    )

    if not otp:
        raise HTTPException(status_code=401, detail="Invalid OTP code")

    now = datetime.now(timezone.utc)                    # ← always aware UTC
    expires = ensure_aware_utc(otp.expires_at)          # ← normalize DB value

    if expires and expires < now:
        raise HTTPException(status_code=410, detail="OTP code expired")

    if otp.verified:
        return {"message": "OTP code already verified", "verified": True}

    # ✅ Write aware UTC — PostgreSQL will store it correctly
    otp.verified = True
    otp.expires_at = now + timedelta(minutes=SESSION_TTL_MINUTES)
    db.commit()
    db.refresh(otp)  # ← ADD THIS

    logger.error(
        "VERIFY_OTP committed: otp_id=%s verified=%s expires_at=%s",
        otp.id, otp.verified, otp.expires_at
    )

    return {"message": "OTP code verified successfully", "verified": True}


def verify_auditee_portal_otp(
    plant: str,
    email: str,
    access_mode: str,
    code: str,
    db: Session,
) -> dict:
    _assert_northwind_email(email)
    normalized_plant = _normalize_portal_plant(plant)
    normalized_email = _normalize_portal_email(email)
    normalized_mode = _normalize_access_mode(access_mode)

    _assert_portal_access_allowed(
        plant=normalized_plant,
        email=normalized_email,
        access_mode=normalized_mode,
        db=db,
    )

    otp = (
        db.query(AuditeePortalEmailOTP)
        .filter_by(
            plant=normalized_plant,
            email=normalized_email,
            access_mode=normalized_mode,
            code=code,
        )
        .order_by(AuditeePortalEmailOTP.expires_at.desc())
        .first()
    )

    if not otp:
        raise HTTPException(status_code=401, detail="Invalid OTP code")

    now = datetime.now(timezone.utc)
    expires = ensure_aware_utc(otp.expires_at)
    if expires and expires < now:
        raise HTTPException(status_code=410, detail="OTP code expired")

    otp.verified = True
    session = _create_portal_session(
        plant=normalized_plant,
        email=normalized_email,
        access_mode=normalized_mode,
        db=db,
    )
    return {
        "message": "OTP code verified successfully",
        "verified": True,
        "session_token": session.session_token,
        "session_expires_at": session.expires_at.isoformat(),
        "access_mode": normalized_mode,
    }

def _get_verified_otp(car, email, db, check_expiry=True):
    db.expire_all()  # ✅ always read fresh from DB

    otp = (
        db.query(CorrectiveActionEmailOTP)
        .filter(
            CorrectiveActionEmailOTP.corrective_action_id == car.id,
            CorrectiveActionEmailOTP.email == email,
            CorrectiveActionEmailOTP.verified == True,
        )
        .order_by(CorrectiveActionEmailOTP.expires_at.desc())
        .first()
    )

    if not otp:
        raise HTTPException(
            status_code=403,
            detail="Email not verified. Please request a new OTP code.",
        )

    if check_expiry:
        now = datetime.now(timezone.utc)
        expires = ensure_aware_utc(otp.expires_at)

        logger.warning(
            "SESSION CHECK: otp_id=%s expires=%s now=%s remaining=%.1fs",
            otp.id, expires, now,
            (expires - now).total_seconds() if expires else 0,
        )

        if expires and expires < now:
            raise HTTPException(
                status_code=410,
                detail="Session expired. Please verify your email again.",
            )

    return otp


# ---------------------------------------------------------------------------
# Form data retrieval
# ---------------------------------------------------------------------------

def get_car_form_data(
    token: str,
    email: str,
    db: Session,
    portal_session_token: str | None = None,
    portal_plant: str | None = None,
    portal_access_mode: str = "auditee",
) -> dict:
    """
    Step 3: return CAR display data + any pre-filled answers.
    OTP must already be verified.
    """
    car = get_car_from_token(token, db)
    _assert_email_authorized(car, email)

    if portal_session_token:
        audit = db.query(Audit).filter_by(id=car.audit_id).first()
        if not audit:
            raise HTTPException(status_code=404, detail="Audit not found")
        _assert_portal_access_allowed(
            plant=portal_plant or str(audit.plant or ""),
            email=email,
            access_mode=portal_access_mode,
            db=db,
        )
        _get_valid_portal_session(
            plant=portal_plant or str(audit.plant or ""),
            email=email,
            access_mode=portal_access_mode,
            session_token=portal_session_token,
            db=db,
        )
    else:
        _get_verified_otp(car, email, db)  # raises if not verified / expired

    audit = db.query(Audit).filter_by(id=car.audit_id).first()
    is_submitted = is_car_locked(car)

    from app.models.document import Document

    # Documents uploaded by the auditee for the CAR solution.
    documents_query = (
        db.query(Document)
        .filter(
            Document.corrective_action_id == car.id,
            Document.audit_answer_id.is_(None),
        )
        .all()
    )

    # Finding-evidence documents the auditor attached to this non-conformity —
    # shown to the auditee (no separate gate) so they can review what the
    # auditor actually observed while building their corrective action.
    finding_evidence_query = (
        db.query(Document)
        .filter(Document.audit_answer_id == car.audit_answer_id)
        .all()
        if car.audit_answer_id
        else []
    )

    def _serialize_doc(doc):
        return {
            "id": doc.id,
            "filename": doc.filename,
            "file_url": get_fresh_doc_url(doc.file_url),
            "size": doc.size,
            "uploaded_at": (
                doc.uploaded_at.strftime("%d/%m/%Y %H:%M")
                if doc.uploaded_at
                else None
            ),
        }

    documents = [_serialize_doc(doc) for doc in documents_query]
    finding_evidence = [_serialize_doc(doc) for doc in finding_evidence_query]

    linked_action = None
    if car.linked_action is not None:
        linked_car = car.linked_action
        linked_docs_query = (
            db.query(Document)
            .filter(
                Document.corrective_action_id == linked_car.id,
                Document.audit_answer_id.is_(None),
            )
            .all()
        )
        linked_action = {
            "car_id": linked_car.id,
            "action_type": linked_car.action_type,
            "implemented_solution": linked_car.implemented_solution or "",
            "root_cause": linked_car.root_cause or "",
            "is_submitted": is_car_locked(linked_car),
            "status": linked_car.status,
            "submitted_at": (
                linked_car.submitted_at.strftime("%d/%m/%Y %H:%M")
                if linked_car.submitted_at
                else None
            ),
            "submission_due_at": (
                linked_car.submission_due_at.strftime("%d/%m/%Y %H:%M")
                if linked_car.submission_due_at
                else None
            ),
            "closure_due_at": (
                linked_car.closure_due_at.strftime("%d/%m/%Y %H:%M")
                if linked_car.closure_due_at
                else None
            ),
            "documents": [_serialize_doc(doc) for doc in linked_docs_query],
        }

    return {
        "action_type": car.action_type,
        "linked_action": linked_action,
        "audit_number": audit.audit_number if audit else "N/A",
        "audit_plant": audit.plant if audit else "N/A",
        "audit_type": (
            audit.questionnaire.name
            if audit and audit.questionnaire
            else "N/A"
        ),
        "auditee_name": email.split("@")[0],
        "reason_why": car.reason_why or "",
        "due_date": (
            car.due_date.strftime("%d/%m/%Y") if car.due_date else "Not defined"
        ),
        # AuditAnswer.finding_text covers app-native CARs; migrated CARs have
        # no AuditAnswer, so fall back to the finding text backfilled from
        # the Monday.com migration.
        "finding": car.finding or (car.answer.finding_text if car.answer else None) or "N/A",
        # Pre-filled fields – empty string when not yet filled
        "implemented_solution": car.implemented_solution or "",
        "root_cause": car.root_cause or "",
        "is_submitted": is_submitted,
        "status": car.status,
        "submitted_at": (
            car.submitted_at.strftime("%d/%m/%Y %H:%M")
            if car.submitted_at
            else None
        ),
        "documents": documents,
        "finding_evidence": finding_evidence,
        "reassigned_at": (
            car.reassigned_at.strftime("%d/%m/%Y %H:%M")
            if car.reassigned_at
            else None
        ),
        "reassigned_from_email": car.reassigned_from_email,
        "cc_emails": _parse_cc_emails(car),
        "can_reassign": not is_submitted and car.reassigned_at is None,
        # Who actually submitted and from where — any invited auditee on the
        # audit can submit any of its CARs, so this can differ from the CAR's
        # current assignee.
        "submitted_by_email": car.submitted_by_email,
        "submission_channel": car.submission_channel,
        # Rejection history + related requirement context — this is the panel
        # the auditee reworks a rejected CAR from, so it's where the latest
        # rejection reason and the underlying question/clause/process matter most.
        "rejection_reason": _latest_rejection_reason(car),
        "review_history": _serialize_review_history(car),
        "related_requirement": _serialize_related_requirement(car),
        # Immediate-action CARs carry accelerated 24h-submit / 48h-close
        # deadlines instead of the regular due date — surface them here so
        # the auditee sees the same urgency on the form as in the email.
        "immediate_action_required": bool(car.immediate_action_required),
        "submission_due_at": (
            car.submission_due_at.strftime("%d/%m/%Y %H:%M")
            if car.submission_due_at
            else None
        ),
        "closure_due_at": (
            car.closure_due_at.strftime("%d/%m/%Y %H:%M")
            if car.closure_due_at
            else None
        ),
    }


def get_auditee_portal_plants(db: Session) -> list[str]:
    rows = (
        db.query(Audit.plant)
        .join(CorrectiveAction, CorrectiveAction.audit_id == Audit.id)
        .filter(CorrectiveAction.auditee_id.isnot(None))
        .distinct()
        .order_by(Audit.plant.asc())
        .all()
    )
    return [row[0] for row in rows if row[0]]


def _serialize_portal_document(doc: Document) -> dict:
    return {
        "id": doc.id,
        "filename": doc.filename,
        "size": doc.size,
        "file_url": get_fresh_doc_url(doc.file_url),
        "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
        "uploaded_by": doc.uploaded_by,
    }


def _group_documents_for_portal(db: Session, car_ids: list[int], answer_ids: list[int]) -> tuple[dict[int, list[dict]], dict[int, list[dict]]]:
    finding_docs: dict[int, list[dict]] = {}
    submission_docs: dict[int, list[dict]] = {}

    if answer_ids:
        docs = (
            db.query(Document)
            .filter(Document.audit_answer_id.in_(answer_ids))
            .all()
        )
        for doc in docs:
            if doc.audit_answer_id is not None:
                finding_docs.setdefault(doc.audit_answer_id, []).append(_serialize_portal_document(doc))

    if car_ids:
        docs = (
            db.query(Document)
            .filter(
                Document.corrective_action_id.in_(car_ids),
                Document.audit_answer_id.is_(None),
            )
            .all()
        )
        for doc in docs:
            if doc.corrective_action_id is not None:
                submission_docs.setdefault(doc.corrective_action_id, []).append(_serialize_portal_document(doc))

    return finding_docs, submission_docs


def get_auditee_portal_data(
    plant: str,
    email: str,
    access_mode: str,
    session_token: str,
    db: Session,
    status: str | None = None,
) -> dict:
    _assert_northwind_email(email)
    normalized_plant = _normalize_portal_plant(plant)
    normalized_email = _normalize_portal_email(email)
    normalized_mode = _normalize_access_mode(access_mode)

    _assert_portal_access_allowed(
        plant=normalized_plant,
        email=normalized_email,
        access_mode=normalized_mode,
        db=db,
    )
    _get_valid_portal_session(
        plant=normalized_plant,
        email=normalized_email,
        access_mode=normalized_mode,
        session_token=session_token,
        db=db,
    )

    cars = _query_auditee_portal_cars(
        normalized_plant,
        normalized_email,
        normalized_mode,
        db,
        status=status,
    )

    answer_ids = [car.audit_answer_id for car in cars if car.audit_answer_id is not None]
    car_ids = [car.id for car in cars]
    finding_docs_by_answer_id, submission_docs_by_car_id = _group_documents_for_portal(db, car_ids, answer_ids)

    status_counts: dict[str, int] = {}
    grouped: dict[int, dict] = {}
    auditee_emails: set[str] = set()

    for car in cars:
        audit = car.audit
        if not audit:
            continue

        # Immediate rows are reached through their linked corrective row (see
        # linked_action below), not as a standalone card -- otherwise an
        # immediate+corrective pair would double-count as 2 findings here.
        if car.action_type == ACTION_TYPE_IMMEDIATE:
            continue

        car_status = normalize_status(car.status)
        status_counts[car_status] = status_counts.get(car_status, 0) + 1
        if car.auditee and car.auditee.email:
            auditee_emails.add(car.auditee.email.strip().lower())

        audit_entry = grouped.setdefault(
            audit.id,
            {
                "audit_id": audit.id,
                "audit_number": audit.audit_number,
                "plant": str(audit.plant) if audit.plant is not None else normalized_plant,
                "sector": audit.sector,
                "status": audit.status,
                # Which checklist/standard this audit was run against (e.g.
                # "IATF Checklist", "VDA 6.3", "Plant Manager IATF Checklist"),
                # so the auditee knows the context their CARs were raised in.
                "questionnaire_name": audit.questionnaire.name if audit.questionnaire else None,
                "planned_start_date": audit.planned_start_date.isoformat() if audit.planned_start_date else None,
                "planned_end_date": audit.planned_end_date.isoformat() if audit.planned_end_date else None,
                "auditee_count": len({(a.email or "").strip().lower() for a in (audit.auditees or []) if getattr(a, "email", None)}),
                # Every auditee invited to this audit can act on any of its CARs
                # (see verify_email_for_car) — surface the actual list, not just
                # the count, so the auditee can see who else shares that access.
                "auditee_emails": sorted({
                    (a.email or "").strip().lower()
                    for a in (audit.auditees or [])
                    if getattr(a, "email", None)
                }),
                "leave_url": None,
                "cars": [],
            },
        )

        if normalized_mode == "auditee" and not audit_entry["leave_url"]:
            leave_token = get_or_create_unavailability_form_token(
                db=db,
                audit_id=audit.id,
                email=normalized_email,
            )
            audit_entry["leave_url"] = build_unavailability_url(leave_token)

        token = get_or_create_car_token(db, car)

        linked_action = None
        if car.linked_action is not None:
            linked_car = car.linked_action
            linked_action = {
                "car_id": linked_car.id,
                "action_type": linked_car.action_type,
                "status": normalize_status(linked_car.status),
                "submitted_at": linked_car.submitted_at.isoformat() if linked_car.submitted_at else None,
                "submission_due_at": linked_car.submission_due_at.isoformat() if linked_car.submission_due_at else None,
                "closure_due_at": linked_car.closure_due_at.isoformat() if linked_car.closure_due_at else None,
                "can_submit": normalized_mode == "auditee" and is_car_editable(linked_car),
                "submission_evidence": submission_docs_by_car_id.get(linked_car.id, []),
                "submission_evidence_count": len(submission_docs_by_car_id.get(linked_car.id, [])),
            }

        audit_entry["cars"].append(
            {
                "car_id": car.id,
                "identifier": car.identifier,
                "action_type": car.action_type,
                "linked_action": linked_action,
                "question": getattr(getattr(car.answer, "question", None), "description", None),
                "finding": car.finding or (car.answer.finding_text if car.answer else None),
                "reason_why": car.reason_why,
                "due_date": car.due_date.isoformat() if car.due_date else None,
                "status": car_status,
                "submitted_at": car.submitted_at.isoformat() if car.submitted_at else None,
                "created_at": car.created_at.isoformat() if car.created_at else None,
                "can_submit": normalized_mode == "auditee" and is_car_editable(car),
                "form_url": build_car_form_url(token),
                "auditee_email": car.auditee.email if car.auditee and car.auditee.email else None,
                "finding_evidence": finding_docs_by_answer_id.get(car.audit_answer_id or -1, []),
                "submission_evidence": submission_docs_by_car_id.get(car.id, []),
                "finding_evidence_count": len(finding_docs_by_answer_id.get(car.audit_answer_id or -1, [])),
                "submission_evidence_count": len(submission_docs_by_car_id.get(car.id, [])),
                "submitted_by_email": car.submitted_by_email,
                "submission_channel": car.submission_channel,
                # Rejection history + related requirement context, so the
                # auditee sees why a CAR was rejected (not just that it was)
                # and exactly which question/clause/process it relates to.
                "rejection_reason": _latest_rejection_reason(car),
                "review_history": _serialize_review_history(car),
                "related_requirement": _serialize_related_requirement(car),
                # Immediate-action CARs carry accelerated 24h-submit /
                # 48h-close deadlines instead of the regular due date.
                "immediate_action_required": bool(car.immediate_action_required),
                "submission_due_at": car.submission_due_at.isoformat() if car.submission_due_at else None,
                "closure_due_at": car.closure_due_at.isoformat() if car.closure_due_at else None,
            }
        )

    audits = sorted(grouped.values(), key=lambda item: item["planned_start_date"] or "", reverse=True)
    return {
        "plant": normalized_plant,
        "email": normalized_email,
        "access_mode": normalized_mode,
        "status_filter": status.strip().lower() if status else None,
        "summary": {
            "total_audits": len(audits),
            # sum(status_counts) rather than len(cars): an immediate+corrective
            # pair shares one status_counts/card entry (see the action_type
            # skip above), so it should read as one finding here too.
            "total_cars": sum(status_counts.values()),
            "total_auditees": len(auditee_emails),
            "status_counts": status_counts,
        },
        "audits": audits,
    }


# ---------------------------------------------------------------------------
# File upload
# ---------------------------------------------------------------------------

def _resolve_target_car(car: CorrectiveAction, target_action_type: str | None) -> CorrectiveAction:
    """Resolve which of a finding's linked rows a request actually targets.

    `car` is always the primary/corrective row (the only one with a token).
    When target_action_type names the linked row instead, switch to it --
    auth/OTP checks stay against `car` since there's no separate token/OTP
    flow for the linked row.
    """
    if target_action_type and target_action_type != car.action_type:
        target_car = car.linked_action
        if target_car is None or target_car.action_type != target_action_type:
            raise HTTPException(
                status_code=404,
                detail=f"No linked '{target_action_type}' action exists for this corrective action.",
            )
        return target_car
    return car


async def upload_file_for_car(
    token: str,
    email: str,
    file: UploadFile,
    db: Session,
    target_action_type: str | None = None,
) -> dict:
    """Upload a single file for a CAR (standalone endpoint, not part of submit)."""
    car = get_car_from_token(token, db)
    _assert_email_authorized(car, email)
    target_car = _resolve_target_car(car, target_action_type)

    if not is_car_editable(target_car):
        raise HTTPException(
            status_code=400,
            detail=f"CAR is not editable in status '{target_car.status}'",
        )

    _get_verified_otp(car, email, db)

    audit = db.query(Audit).filter_by(id=car.audit_id).first()
    audit_ref = audit.audit_number if audit else ""

    upload = await upload_car_document(file, car_id=target_car.id, audit_ref=audit_ref)

    document = Document(
        filename=upload["filename"],
        mimetype=upload["mimetype"],
        size=upload["size"],
        file_url=upload["file_url"],
        corrective_action_id=target_car.id,
        uploaded_at=datetime.now(),
        uploaded_by=email,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    return {
        "message": "File uploaded successfully",
        "document": {
            "id": document.id,
            "filename": document.filename,
            "file_url": document.file_url,
            "size": document.size,
            "uploaded_at": document.uploaded_at.strftime("%d/%m/%Y %H:%M"),
        },
    }


async def delete_file_for_car(
    document_id: int,
    token: str,
    email: str,
    db: Session,
    target_action_type: str | None = None,
) -> dict:
    """Delete a previously uploaded document from Azure and the DB."""
    car = get_car_from_token(token, db)
    _assert_email_authorized(car, email)
    target_car = _resolve_target_car(car, target_action_type)

    document = (
        db.query(Document)
        .filter_by(id=document_id, corrective_action_id=target_car.id)
        .first()
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete from Azure – blob_name is the path after the container
    # file_url format: https://<account>.blob.core.windows.net/<container>/<blob_name>
    blob_name = _extract_blob_name(document.file_url)
    if blob_name:
        await delete_blob(blob_name)

    db.delete(document)
    db.commit()

    return {"message": "File deleted successfully"}

# ---------------------------------------------------------------------------
# Form submission
# ---------------------------------------------------------------------------

async def submit_car_form(
    token: str,
    email: str,
    implemented_solution: str,
    root_cause: str | None,
    files: Optional[List[UploadFile]],
    db: Session,
    portal_session_token: str | None = None,
    portal_plant: str | None = None,
    portal_access_mode: str = "auditee",
    target_action_type: str | None = None,
) -> dict:
    """
    Step 4: persist the solution + root cause, upload files, mark as submitted.

    The token always resolves to the primary/corrective row (only that row has
    a CorrectiveActionAccessToken/OTP). target_action_type lets the caller
    submit the linked immediate row instead through the same token: auth/OTP
    stays checked against the primary `car`, but the actual mutation applies
    to `target_car`.
    """
    car = get_car_from_token(token, db)
    _assert_email_authorized(car, email)

    if portal_session_token:
        audit = db.query(Audit).filter_by(id=car.audit_id).first()
        if not audit:
            raise HTTPException(status_code=404, detail="Audit not found")
        _assert_portal_access_allowed(
            plant=portal_plant or str(audit.plant or ""),
            email=email,
            access_mode=portal_access_mode,
            db=db,
        )
        _get_valid_portal_session(
            plant=portal_plant or str(audit.plant or ""),
            email=email,
            access_mode=portal_access_mode,
            session_token=portal_session_token,
            db=db,
        )
    else:
        _get_verified_otp(car, email, db)

    target_car = _resolve_target_car(car, target_action_type)

    # Already submitted?
    if not is_car_editable(target_car):
        return {
            "message": "This form has already been submitted",
            "car_id": target_car.id,
            "status": target_car.status,
            "already_submitted": True,
            "submitted_at": (
                target_car.submitted_at.strftime("%d/%m/%Y %H:%M")
                if target_car.submitted_at
                else None
            ),
            "previous_solution": target_car.implemented_solution,
        }

    # The immediate row is a containment description, not a root-cause
    # analysis -- it has no 5-Whys requirement.
    if target_car.action_type != ACTION_TYPE_IMMEDIATE:
        _validate_root_cause_format(root_cause)

    audit = db.query(Audit).filter_by(id=car.audit_id).first()
    audit_ref = audit.audit_number if audit else ""

    existing_submission_docs = (
        db.query(Document)
        .filter(
            Document.corrective_action_id == target_car.id,
            Document.audit_answer_id.is_(None),
        )
        .count()
    )
    incoming_file_count = sum(1 for file in files or [] if file and file.filename)
    if existing_submission_docs + incoming_file_count < 1:
        raise HTTPException(
            status_code=400,
            detail="At least one related document is required before submitting the CAR.",
        )

    # Upload files
    uploaded_files: list[dict] = []
    if files:
        for file in files:
            if not (file and file.filename):
                continue

            upload = await upload_car_document(
                file, car_id=target_car.id, audit_ref=audit_ref
            )

            document = Document(
                filename=upload["filename"],
                mimetype=upload["mimetype"],
                size=upload["size"],
                file_url=upload["file_url"],
                corrective_action_id=target_car.id,
                uploaded_at=datetime.now(),
            )
            db.add(document)
            uploaded_files.append(
                {"filename": upload["filename"], "size": upload["size"]}
            )

    # Update CAR fields
    target_car.implemented_solution = implemented_solution
    target_car.root_cause = root_cause
    target_car.status = "submitted"
    target_car.submitted_at = datetime.now()
    target_car.submitted_by_email = email.strip().lower()
    target_car.submission_channel = "portal" if portal_session_token else "form_link"

    # Invalidate OTP session after successful submission. Stays keyed on the
    # primary `car` -- there is no separate OTP flow for the linked row.
    db.query(CorrectiveActionEmailOTP).filter(
        CorrectiveActionEmailOTP.corrective_action_id == car.id,
        CorrectiveActionEmailOTP.email == email,
        CorrectiveActionEmailOTP.verified == True,
    ).update({"verified": False}, synchronize_session=False)

    db.commit()

    # Notify auditor
    auditor_id = audit.auditor_id if audit else None
    if auditor_id:
        await notification_service.create_and_send_notification(
            db=db,
            user_id=auditor_id,
            notification_type="car_submission",
            title="New CAR Submission",
            message=f"Solution submitted for CAR - {audit.audit_number}",
            link=f"/audits/{audit.id}/corrective-actions/{target_car.id}",
            metadata={
                "car_id": target_car.id,
                "audit_id": audit.id,
                "audit_number": audit.audit_number,
                "submitted_by": email,
                "submitted_at": target_car.submitted_at.isoformat(),
                "plant": audit.plant,
                "sector": audit.sector,
            },
        )

    return {
        "message": "Corrective action submitted successfully",
        "car_id": target_car.id,
        "status": target_car.status,
        "already_submitted": False,
        "submitted_at": target_car.submitted_at.strftime("%d/%m/%Y %H:%M"),
        "uploaded_files": uploaded_files,
    }


# ---------------------------------------------------------------------------
# Reassign responsible + "Copy to" recipients (auditee-triggered)
# ---------------------------------------------------------------------------

MAX_CC_EMAILS = 5


def _parse_cc_emails(car: CorrectiveAction) -> list[str]:
    if not car.cc_emails:
        return []
    try:
        parsed = json.loads(car.cc_emails)
        if isinstance(parsed, list):
            return [str(e).strip().lower() for e in parsed if str(e).strip()]
    except Exception:
        pass
    return []


def _serialize_cc_emails(emails: list[str]) -> str:
    return json.dumps(emails)


async def _reassign_car_core(
    car: CorrectiveAction,
    old_email: str,
    new_email: str,
    reason: str | None,
    db: Session,
    initiated_by_auditor: bool,
    actor_name: str | None = None,
) -> dict:
    """Shared reassignment logic: validation, DB update, and notification emails.

    Used by both the auditee self-service flow (reassign_car) and the
    auditor-initiated flow (reassign_car_by_auditor).
    """
    if is_reassignment_blocked(car, initiated_by_auditor):
        detail = (
            "This corrective action has already been accepted or closed and can no longer be reassigned."
            if initiated_by_auditor
            else "This corrective action has already been submitted and can no longer be reassigned."
        )
        raise HTTPException(status_code=400, detail=detail)
    if car.reassigned_at is not None:
        raise HTTPException(
            status_code=400,
            detail="This corrective action has already been reassigned once.",
        )

    normalized_new_email = new_email.strip().lower()
    if normalized_new_email == old_email.strip().lower():
        raise HTTPException(
            status_code=400,
            detail="This corrective action is already assigned to that email.",
        )

    audit = db.query(Audit).filter_by(id=car.audit_id).first()
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    new_auditee = (
        db.query(AuditAuditee)
        .filter(
            AuditAuditee.audit_id == car.audit_id,
            func.lower(AuditAuditee.email) == normalized_new_email,
        )
        .first()
    )
    if not new_auditee:
        new_auditee = AuditAuditee(audit_id=car.audit_id, email=normalized_new_email)
        db.add(new_auditee)
        db.flush()

    car.reassigned_from_email = old_email
    car.auditee_id = new_auditee.id
    car.reassigned_at = datetime.now(timezone.utc)
    car.reassignment_reason = reason

    # Reassignment is only reachable through the primary row's token, so
    # without this the linked immediate/corrective row would silently stay
    # on the old auditee -- keep both halves of a finding on the same person.
    if car.linked_action is not None:
        car.linked_action.reassigned_from_email = old_email
        car.linked_action.auditee_id = new_auditee.id
        car.linked_action.reassigned_at = car.reassigned_at
        car.linked_action.reassignment_reason = reason

    # An auditor may reassign an already-"submitted" CAR (see
    # is_reassignment_blocked above) - but submit_car_form only accepts
    # EDITABLE_STATUSES, so without reopening it here the new auditee would
    # get the "Fill Form" email and then hit "CAR is not editable" the
    # moment they tried to actually submit anything.
    if initiated_by_auditor:
        for target in (car, car.linked_action):
            if target is not None and not is_car_editable(target):
                target.status = "pending"
                target.submitted_at = None

    db.commit()
    db.refresh(car)

    token_str = get_or_create_car_token(db, car)
    form_url = build_car_form_url(token_str)
    unavailability_token = get_or_create_unavailability_form_token(
        db=db, audit_id=audit.id, email=normalized_new_email
    )
    unavailability_url = build_unavailability_url(unavailability_token)
    portal_url = build_auditee_portal_url()
    due_date_str = car.due_date.strftime("%d/%m/%Y") if car.due_date else "Not defined"
    identifier = car.identifier or f"CAR-{car.id}"
    plant_label = audit.plant if audit and audit.plant else "N/A"
    reason_html = reason or "No reason provided."
    actor_label = f"the auditor ({actor_name})" if initiated_by_auditor and actor_name else (
        "the auditor" if initiated_by_auditor else "you"
    )
    actor_label_display = actor_label[0].upper() + actor_label[1:]

    def _email_shell(banner_subtitle: str, banner_title: str, body_inner: str) -> str:
        return f"""
        <div style="max-width:560px;margin:0 auto;font-family:Arial,sans-serif;font-size:14px;color:#1a1a1a;background:#fff;border:1px solid #e5e5e5;border-radius:10px;overflow:hidden;">

        <div style="background:#fff;padding:20px 28px 0;text-align:center;">
            <img src="https://your-app.azurewebsites.net/assets/northwind-CfOjGbwW.png"
                 alt="Northwind" style="max-height:40px;" />
        </div>

        <div style="background:#4338CA;padding:18px 28px;margin-top:16px;">
            <p style="margin:0;font-size:11px;color:#D6D3F7;letter-spacing:0.08em;text-transform:uppercase;">{banner_subtitle}</p>
            <p style="margin:6px 0 0;font-size:18px;font-weight:600;color:#fff;">{banner_title}</p>
        </div>

        <div style="padding:24px 28px;">
            {body_inner}
        </div>

        </div>
        """

    def _info_row(label: str, value: str) -> str:
        return (
            f'<tr><td style="color:#666;padding:5px 0;width:40%;">{label}</td>'
            f'<td style="font-weight:600;padding:5px 0;">{value}</td></tr>'
        )

    try:
        info_rows = "".join([
            _info_row("Audit number", audit.audit_number),
            _info_row("Plant", plant_label),
            _info_row("CAR reference", identifier),
            _info_row("Due date", due_date_str),
            _info_row("Reassigned by", actor_label_display),
        ])
        body_inner = f"""
            <p style="margin:0 0 20px;line-height:1.6;">A corrective action has been reassigned to you by {actor_label}. Please review the details below and complete the form before the due date.</p>

            <div style="background:#f7f7f5;border-radius:8px;padding:16px 20px;margin-bottom:20px;">
            <table style="width:100%;border-collapse:collapse;font-size:13px;">
                {info_rows}
            </table>
            </div>

            <div style="margin-bottom:20px;">
              <a href="{form_url}" style="display:inline-block;background:#185FA5;color:#fff;text-align:center;padding:11px 20px;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px;margin:0 10px 10px 0;">Fill Form</a>
              <a href="{unavailability_url}" style="display:inline-block;background:#6b7280;color:#fff;text-align:center;padding:11px 20px;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px;margin:0 0 10px 0;">Declare Leave</a>
            </div>

            <div style="background:#EFF6FF;border:1px solid #BFDBFE;border-radius:8px;padding:14px 18px;margin-bottom:20px;">
              <p style="margin:0 0 8px;font-size:13px;color:#1e3a5f;line-height:1.5;">Prefer one place for everything? Open the portal to view and complete all your corrective actions using your Northwind email.</p>
              <a href="{portal_url}" style="display:inline-block;background:#1B5E20;color:#fff;text-align:center;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:600;font-size:13px;">Go to My Portal</a>
            </div>

            <p style="margin:0;font-size:12px;color:#888;line-height:1.6;border-top:1px solid #eee;padding-top:16px;">If you believe this was assigned to you in error, please contact your auditor directly. Do not reply to this email.</p>
        """
        await send_email(
            subject=f"Corrective Action Reassigned To You - {audit.audit_number}",
            recipients=[normalized_new_email],
            db=db,
            context="car_reassigned_new_auditee",
            body_html=_email_shell(
                f"Corrective action report &middot; {identifier}",
                "Reassigned to you",
                body_inner,
            ),
        )
    except Exception:
        logger.exception("Failed to notify new CAR auditee %s", normalized_new_email)

    try:
        info_rows = "".join([
            _info_row("Audit number", audit.audit_number),
            _info_row("CAR reference", identifier),
            _info_row("Reassigned to", normalized_new_email),
            _info_row("Reassigned by", actor_label_display),
        ])
        body_inner = f"""
            <p style="margin:0 0 20px;line-height:1.6;">This corrective action has been reassigned to <strong>{normalized_new_email}</strong> by {actor_label}. You are no longer responsible for it.</p>

            <div style="background:#f7f7f5;border-radius:8px;padding:16px 20px;margin-bottom:20px;">
            <table style="width:100%;border-collapse:collapse;font-size:13px;">
                {info_rows}
            </table>
            </div>

            <div style="border-left:3px solid #4338CA;background:#EEF2FF;padding:12px 16px;margin-bottom:8px;">
            <p style="margin:0 0 4px;font-size:12px;font-weight:600;color:#4338CA;">Reason</p>
            <p style="margin:0;color:#3730A3;line-height:1.6;">{reason_html}</p>
            </div>

            <p style="margin:20px 0 0;font-size:12px;color:#888;line-height:1.6;border-top:1px solid #eee;padding-top:16px;">Do not reply to this email.</p>
        """
        await send_email(
            subject=f"Corrective Action Reassigned - {audit.audit_number}",
            recipients=[old_email],
            db=db,
            context="car_reassigned_old_auditee",
            body_html=_email_shell(
                f"Corrective action report &middot; {identifier}",
                "Reassigned",
                body_inner,
            ),
        )
    except Exception:
        logger.exception("Failed to notify old CAR auditee %s", old_email)

    supervisor_recipients = [
        e for e in [
            getattr(getattr(audit, "auditor", None), "email", None),
            getattr(audit, "supervisor_email", None),
        ] if e
    ]
    if supervisor_recipients:
        try:
            info_rows = "".join([
                _info_row("Audit number", audit.audit_number),
                _info_row("CAR reference", identifier),
                _info_row("From", old_email),
                _info_row("To", normalized_new_email),
                _info_row("Reassigned by", actor_label_display),
            ])
            body_inner = f"""
                <p style="margin:0 0 20px;line-height:1.6;">A corrective action's auditee was reassigned by {actor_label}.</p>

                <div style="background:#f7f7f5;border-radius:8px;padding:16px 20px;margin-bottom:20px;">
                <table style="width:100%;border-collapse:collapse;font-size:13px;">
                    {info_rows}
                </table>
                </div>

                <div style="border-left:3px solid #4338CA;background:#EEF2FF;padding:12px 16px;margin-bottom:8px;">
                <p style="margin:0 0 4px;font-size:12px;font-weight:600;color:#4338CA;">Reason</p>
                <p style="margin:0;color:#3730A3;line-height:1.6;">{reason_html}</p>
                </div>

                <p style="margin:20px 0 0;font-size:12px;color:#888;line-height:1.6;border-top:1px solid #eee;padding-top:16px;">Do not reply to this email.</p>
            """
            await send_email(
                subject=f"CAR Reassigned - {audit.audit_number}",
                recipients=supervisor_recipients,
                db=db,
                context="car_reassigned_supervisor_notice",
                body_html=_email_shell(
                    f"Corrective action report &middot; {identifier}",
                    "Auditee reassigned",
                    body_inner,
                ),
            )
        except Exception:
            logger.exception("Failed to notify auditor/supervisor of CAR reassignment")

    return {
        "message": "Corrective action reassigned successfully",
        "car_id": car.id,
        "reassigned_from_email": old_email,
        "reassigned_to_email": normalized_new_email,
        "reassigned_at": car.reassigned_at.isoformat(),
    }


async def reassign_car(
    token: str,
    email: str,
    new_email: str,
    reason: str | None,
    db: Session,
    portal_session_token: str | None = None,
    portal_plant: str | None = None,
    portal_access_mode: str = "auditee",
) -> dict:
    """Auditee-triggered, one-time handoff of CAR responsibility to someone else."""
    car = get_car_from_token(token, db)
    _assert_email_authorized(car, email)

    # Same dual-auth pattern as get_car_form_data / submit_car_form: a valid
    # portal session (auditee already OTP-verified at the plant/email level)
    # stands in for the per-CAR OTP check used by the standalone form link.
    if portal_session_token:
        audit = db.query(Audit).filter_by(id=car.audit_id).first()
        if not audit:
            raise HTTPException(status_code=404, detail="Audit not found")
        _assert_portal_access_allowed(
            plant=portal_plant or str(audit.plant or ""),
            email=email,
            access_mode=portal_access_mode,
            db=db,
        )
        _get_valid_portal_session(
            plant=portal_plant or str(audit.plant or ""),
            email=email,
            access_mode=portal_access_mode,
            session_token=portal_session_token,
            db=db,
        )
    else:
        _get_verified_otp(car, email, db)

    return await _reassign_car_core(
        car, email, new_email, reason, db, initiated_by_auditor=False
    )


async def reassign_car_by_auditor(
    car_id: int,
    new_email: str,
    reason: str | None,
    db: Session,
    actor_name: str | None = None,
) -> dict:
    """Auditor-triggered, one-time handoff of CAR responsibility to someone else."""
    car = db.query(CorrectiveAction).filter(CorrectiveAction.id == car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="Corrective action not found")
    if not car.auditee or not car.auditee.email:
        raise HTTPException(
            status_code=400,
            detail="This corrective action has no auditee assigned yet.",
        )
    old_email = car.auditee.email
    return await _reassign_car_core(
        car,
        old_email,
        new_email,
        reason,
        db,
        initiated_by_auditor=True,
        actor_name=actor_name,
    )


async def add_car_cc(
    token: str,
    email: str,
    cc_emails: list[str],
    db: Session,
    portal_session_token: str | None = None,
    portal_plant: str | None = None,
    portal_access_mode: str = "auditee",
) -> dict:
    """Auditee-triggered: add extra people to be copied on this CAR's notifications."""
    car = get_car_from_token(token, db)
    _assert_email_authorized(car, email)

    # Same dual-auth pattern as get_car_form_data / submit_car_form / reassign_car.
    if portal_session_token:
        audit_for_auth = db.query(Audit).filter_by(id=car.audit_id).first()
        if not audit_for_auth:
            raise HTTPException(status_code=404, detail="Audit not found")
        _assert_portal_access_allowed(
            plant=portal_plant or str(audit_for_auth.plant or ""),
            email=email,
            access_mode=portal_access_mode,
            db=db,
        )
        _get_valid_portal_session(
            plant=portal_plant or str(audit_for_auth.plant or ""),
            email=email,
            access_mode=portal_access_mode,
            session_token=portal_session_token,
            db=db,
        )
    else:
        _get_verified_otp(car, email, db)

    existing = _parse_cc_emails(car)
    auditee_email = email.strip().lower()

    incoming = [e.strip().lower() for e in cc_emails if e and e.strip()]
    newly_added: list[str] = []
    merged = list(existing)
    for candidate in incoming:
        if candidate == auditee_email or candidate in merged:
            continue
        merged.append(candidate)
        newly_added.append(candidate)

    if len(merged) > MAX_CC_EMAILS:
        raise HTTPException(
            status_code=400,
            detail=f"A corrective action can have at most {MAX_CC_EMAILS} people in copy.",
        )

    car.cc_emails = _serialize_cc_emails(merged)
    db.commit()

    if newly_added:
        audit = db.query(Audit).filter_by(id=car.audit_id).first()
        identifier = car.identifier or f"CAR-{car.id}"
        due_date_str = car.due_date.strftime("%d/%m/%Y") if car.due_date else "Not defined"
        for cc_email in newly_added:
            try:
                await send_email(
                    subject=f"You've been copied on a Corrective Action - {audit.audit_number if audit else ''}",
                    recipients=[cc_email],
                    db=db,
                    context="car_cc_added",
                    body_html=(
                        f"<p>Hello,</p>"
                        f"<p>You've been added in copy on corrective action "
                        f"<strong>{identifier}</strong>"
                        + (f" for audit <strong>{audit.audit_number}</strong>." if audit else ".")
                        + "</p>"
                        f"<p><strong>Status:</strong> {car.status}<br/>"
                        f"<strong>Due date:</strong> {due_date_str}</p>"
                        f"<p>This is a visibility-only notice; you don't need to take action.</p>"
                    ),
                )
            except Exception:
                logger.exception("Failed to notify new CC recipient %s", cc_email)

    return {
        "message": "Copy list updated",
        "car_id": car.id,
        "cc_emails": merged,
    }


# ---------------------------------------------------------------------------
# Unavailability + due-date recomputation
# (moved from the inline router implementation)
# ---------------------------------------------------------------------------

def check_period_overlap(
    new_start: date,
    new_end: date,
    existing_periods: list[Tuple[date, date]],
) -> Tuple[bool, list[Tuple[date, date]]]:
    """Return (has_overlap, list_of_overlapping_periods)."""
    overlapping = [
        (s, e)
        for s, e in existing_periods
        if new_start <= e and new_end >= s
    ]
    return bool(overlapping), overlapping


def _resolve_plant_manager_email(plant: Optional[str]) -> str:
    key = (plant or "").strip().lower()
    if "." in key:
        key = key.split(".")[-1]
    emails = PLANT_MANAGER_EMAILS.get(key, [])
    if emails:
        # Return the first manager email in the list (primary contact)
        return emails[0].strip().lower()
    raise HTTPException(
        status_code=400,
        detail=f"No plant manager configured for plant '{plant}'.",
    )


def _build_pm_approval_email_html(
    *,
    audit_number: str,
    plant: str,
    sector: str | None,
    requested_by_email: str,
    start_date: date,
    end_date: date,
    reason: Optional[str],
    approve_url: str,
    reject_url: str,
) -> str:
    reason_html = reason or "No reason provided."
    return f"""
    <html>
      <body style="font-family:Arial,sans-serif;background:#f5f7fb;padding:24px;">
        <div style="max-width:700px;margin:auto;background:#fff;border:1px solid #e6e8ef;border-radius:10px;padding:24px;">
          <h2 style="margin-top:0;color:#1f3a8a;">Leave Declaration Approval Needed</h2>
          <p>Auditee leave has been declared for audit <strong>{audit_number}</strong>.</p>
          <table style="border-collapse:collapse;width:100%;margin:14px 0;">
            <tr><td style="padding:8px;border:1px solid #ddd;"><strong>Plant</strong></td><td style="padding:8px;border:1px solid #ddd;">{plant}</td></tr>
            <tr><td style="padding:8px;border:1px solid #ddd;"><strong>Sector</strong></td><td style="padding:8px;border:1px solid #ddd;">{sector or "N/A"}</td></tr>
            <tr><td style="padding:8px;border:1px solid #ddd;"><strong>Requested by</strong></td><td style="padding:8px;border:1px solid #ddd;">{requested_by_email}</td></tr>
            <tr><td style="padding:8px;border:1px solid #ddd;"><strong>Start</strong></td><td style="padding:8px;border:1px solid #ddd;">{start_date.strftime("%d/%m/%Y")}</td></tr>
            <tr><td style="padding:8px;border:1px solid #ddd;"><strong>End</strong></td><td style="padding:8px;border:1px solid #ddd;">{end_date.strftime("%d/%m/%Y")}</td></tr>
            <tr><td style="padding:8px;border:1px solid #ddd;"><strong>Reason</strong></td><td style="padding:8px;border:1px solid #ddd;">{reason_html}</td></tr>
          </table>
          <p>Choose one action:</p>
          <div style="margin-top:18px;">
            <a href="{approve_url}" style="display:inline-block;background:#15803d;color:#fff;text-decoration:none;padding:10px 18px;border-radius:6px;font-weight:600;margin-right:8px;">Approve</a>
            <a href="{reject_url}" style="display:inline-block;background:#b91c1c;color:#fff;text-decoration:none;padding:10px 18px;border-radius:6px;font-weight:600;">Reject</a>
          </div>
          <p style="margin-top:20px;color:#666;font-size:12px;">This action link is single-use and expires in 7 days.</p>
        </div>
      </body>
    </html>
    """


def _notify_auditor_unavailability_decision(
    db: Session,
    audit: Audit,
    unavailability: AuditUnavailability,
) -> None:
    if not audit.auditor_id:
        return

    decision = (unavailability.status or "").lower()
    if decision == "approved":
        title = "Leave Request Approved"
        message = (
            f"Auditee leave approved for audit {audit.audit_number}. "
            "CAR due dates were recalculated."
        )
    else:
        title = "Leave Request Rejected"
        message = (
            f"Auditee leave rejected for audit {audit.audit_number}. "
            "CAR due dates were not modified."
        )

    asyncio.run(
        notification_service.create_and_send_notification(
            db=db,
            user_id=audit.auditor_id,
            notification_type="unavailability_decision",
            title=title,
            message=message,
            link=f"/audits/{audit.id}",
            metadata={
                "audit_id": audit.id,
                "audit_number": audit.audit_number,
                "unavailability_id": unavailability.id,
                "status": unavailability.status,
                "start_date": unavailability.start_date.isoformat(),
                "end_date": unavailability.end_date.isoformat(),
                "decision_by_email": unavailability.decision_by_email,
            },
        )
    )


def _notify_auditees_unavailability_decision(
    db: Session,
    audit: Audit,
    unavailability: AuditUnavailability,
) -> None:
    requester_email = (unavailability.requested_by_email or "").strip().lower()
    auditee_pool = {
        (a.email or "").strip().lower()
        for a in (audit.auditees or [])
        if getattr(a, "email", None)
    }
    if requester_email and requester_email in auditee_pool:
        auditee_emails = [requester_email]
    else:
        auditee_emails = sorted(auditee_pool)
    if not auditee_emails:
        return

    decision = (unavailability.status or "").lower()
    is_approved = decision == "approved"
    status_label = "Approved" if is_approved else "Rejected"
    color = "#15803d" if is_approved else "#b91c1c"
    message = (
        "Your leave request was approved. CAR due dates were recalculated accordingly."
        if is_approved
        else "Your leave request was rejected. CAR due dates remain unchanged."
    )
    period = (
        f"{unavailability.start_date.strftime('%d/%m/%Y')} - "
        f"{unavailability.end_date.strftime('%d/%m/%Y')}"
    )
    reason = unavailability.reason or "No reason provided."
    body_html = f"""
    <html>
      <body style="font-family:Arial,sans-serif;background:#f8fafc;padding:24px;">
        <div style="max-width:700px;margin:auto;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:24px;">
          <h2 style="margin-top:0;color:{color};">Leave Request {status_label}</h2>
          <p>Your leave request for audit <strong>{audit.audit_number}</strong> has been processed.</p>
          <table style="border-collapse:collapse;width:100%;margin:14px 0;">
            <tr><td style="padding:8px;border:1px solid #ddd;"><strong>Plant</strong></td><td style="padding:8px;border:1px solid #ddd;">{audit.plant}</td></tr>
            <tr><td style="padding:8px;border:1px solid #ddd;"><strong>Period</strong></td><td style="padding:8px;border:1px solid #ddd;">{period}</td></tr>
            <tr><td style="padding:8px;border:1px solid #ddd;"><strong>Requested reason</strong></td><td style="padding:8px;border:1px solid #ddd;">{reason}</td></tr>
          </table>
          <p style="margin-top:16px;">{message}</p>
        </div>
      </body>
    </html>
    """

    try:
        asyncio.run(
            send_email(
                subject=f"Leave Request {status_label} - Audit {audit.audit_number}",
                recipients=auditee_emails,
                db=db,
                context="leave_decision_auditee",
                body_html=body_html,
            )
        )
    except Exception:
        logger.exception(
            "Failed to send leave decision email to auditees for audit %s",
            audit.id,
        )


def _recompute_due_dates_for_audit(
    db: Session,
    audit: Audit,
) -> list[dict]:
    approved_periods = _to_date_pairs(
        db.query(AuditUnavailability)
        .filter(
            AuditUnavailability.audit_id == audit.id,
            AuditUnavailability.status == "approved",
        )
        .all()
    )

    cars = db.query(CorrectiveAction).filter_by(audit_id=audit.id).all()
    recalculated: list[dict] = []

    for car in cars:
        if not car.created_at:
            logger.warning("Skipping CAR %s: no created_at", car.id)
            continue

        if not car.due_date_base:
            car.due_date_base = car.due_date

        old_due = car.due_date
        try:
            car.due_date = recompute_due_date_from_base(
                created_at=car.created_at,
                plant=audit.plant,
                due_base=car.due_date_base,
                unavailability_periods=approved_periods,
            )
        except Exception as exc:
            logger.exception("Error recalculating CAR %s", car.id)
            raise HTTPException(
                status_code=500,
                detail=f"Error recalculating due date: {exc}",
            )

        if car.due_date != old_due:
            db.add(
                CarEscalation(
                    corrective_action_id=car.id,
                    escalated_at=datetime.utcnow(),
                    email_sent_to=(car.auditee.email if car.auditee else None),
                    comment=(
                        "DUE_DATE_RECOMPUTED_LEAVE_APPROVED"
                        f"|old={(old_due.isoformat() if old_due else 'None')}"
                        f"|new={(car.due_date.isoformat() if car.due_date else 'None')}"
                    ),
                )
            )

        recalculated.append(
            {
                "car_id": car.id,
                "old_due_date": old_due.isoformat() if old_due else None,
                "new_due_date": car.due_date.isoformat() if car.due_date else None,
                "changed": car.due_date != old_due,
            }
        )

    return recalculated


def request_audit_unavailability_approval(
    db: Session,
    start_date,
    end_date,
    reason: Optional[str],
    token: str,
) -> dict:
    """
    Create a pending leave request and ask the plant manager to approve/reject it.
    Due dates are recomputed only when approved.
    """
    if isinstance(start_date, datetime):
        start_date = start_date.date()
    if isinstance(end_date, datetime):
        end_date = end_date.date()

    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="Start date must be before or equal to end date.",
        )

    access_token = get_unavailability_access_token(db, token)
    if access_token.unavailability_id is not None:
        raise HTTPException(
            status_code=403,
            detail="This token cannot be used to declare leave.",
        )
    audit = db.query(Audit).filter_by(id=access_token.audit_id).first()
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    audit_auditee_emails = {
        (a.email or "").strip().lower()
        for a in (audit.auditees or [])
        if getattr(a, "email", None)
    }
    if (access_token.email or "").strip().lower() not in audit_auditee_emails:
        raise HTTPException(
            status_code=403,
            detail="Token email is not authorized to declare leave for this audit.",
        )

    final_pm_email = _resolve_plant_manager_email(str(audit.plant) if audit.plant is not None else None)

    existing_unavailabilities = (
        db.query(AuditUnavailability)
        .filter(
            AuditUnavailability.audit_id == audit.id,
            AuditUnavailability.status.in_(["pending", "approved"]),
        )
        .all()
    )
    existing_periods = _to_date_pairs(existing_unavailabilities)

    has_overlap, overlapping = check_period_overlap(
        start_date, end_date, existing_periods
    )
    if has_overlap:
        detail = ", ".join(
            f"{s.strftime('%d/%m/%Y')}-{e.strftime('%d/%m/%Y')}"
            for s, e in overlapping
        )
        raise HTTPException(
            status_code=409,
            detail=f"This period overlaps with existing unavailability periods: {detail}.",
        )

    today = date.today()
    if end_date < today - timedelta(days=365):
        raise HTTPException(
            status_code=400,
            detail="The unavailability period seems too far in the past. Please check the year entered.",
        )

    ua = AuditUnavailability(
        audit_id=audit.id,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
        status="pending",
        requested_by_email=access_token.email,
        plant_manager_email=final_pm_email,
        created_at=datetime.now(timezone.utc),
    )
    db.add(ua)
    db.flush()

    approval_token = generate_unavailability_token(
        audit_id=audit.id,
        email=final_pm_email,
        unavailability_id=ua.id,
        db=db,
        expires_hours=24 * 7,
        auto_commit=False,
    )
    approve_url = (
        f"{DECISION_BASE_URL}/car/audits/unavailability/decision"
        f"?token={approval_token}&unavailability_id={ua.id}&decision=approve"
    )
    reject_url = (
        f"{DECISION_BASE_URL}/car/audits/unavailability/decision"
        f"?token={approval_token}&unavailability_id={ua.id}&decision=reject"
    )

    db.commit()

    email_sent = True
    try:
        asyncio.run(
            send_email(
                subject=f"Approval Required - Leave declaration ({audit.audit_number})",
                recipients=[final_pm_email],
                db=db,
                context="leave_decision_pm",
                body_html=_build_pm_approval_email_html(
                    audit_number=audit.audit_number,
                    plant=str(audit.plant),
                    sector=audit.sector,
                    requested_by_email=access_token.email,
                    start_date=start_date,
                    end_date=end_date,
                    reason=reason,
                    approve_url=approve_url,
                    reject_url=reject_url,
                ),
            )
        )
    except Exception:
        email_sent = False
        logger.exception(
            "Failed to send leave approval request email to plant manager (audit=%s, ua=%s)",
            audit.id,
            ua.id,
        )
    db.commit()

    return {
        "message": (
            "Leave request submitted and sent to plant manager for approval."
            if email_sent
            else "Leave request submitted, but email delivery to plant manager failed."
        ),
        "audit_id": audit.id,
        "unavailability_id": ua.id,
        "status": ua.status,
        "email_sent": email_sent,
        "plant_manager_email": final_pm_email,
        "unavailability_period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "reason": reason,
        },
    }


def decide_audit_unavailability(
    db: Session,
    *,
    token: str,
    unavailability_id: int,
    decision: str,
    comment: Optional[str] = None,
) -> dict:
    decision_normalized = (decision or "").strip().lower()
    if decision_normalized not in {"approve", "reject"}:
        raise HTTPException(status_code=400, detail="decision must be approve or reject")

    access_token = get_unavailability_access_token(db, token)
    if access_token.unavailability_id is None:
        raise HTTPException(
            status_code=403,
            detail="This token cannot be used for decision.",
        )
    if access_token.used:
        raise HTTPException(status_code=409, detail="This decision link was already used")

    ua = db.query(AuditUnavailability).filter_by(id=unavailability_id).first()
    if not ua:
        raise HTTPException(status_code=404, detail="Unavailability request not found")
    if ua.audit_id != access_token.audit_id:
        raise HTTPException(status_code=400, detail="Token does not match this request")
    if access_token.unavailability_id is not None and access_token.unavailability_id != ua.id:
        raise HTTPException(status_code=400, detail="Token does not match this leave request")
    if ua.plant_manager_email and (
        (access_token.email or "").strip().lower()
        != (ua.plant_manager_email or "").strip().lower()
    ):
        raise HTTPException(status_code=403, detail="Token email is not authorized to decide this request")
    if ua.status != "pending":
        raise HTTPException(status_code=409, detail=f"Request already {ua.status}")

    audit = db.query(Audit).filter_by(id=ua.audit_id).first()
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    ua.status = "approved" if decision_normalized == "approve" else "rejected"
    ua.decision_by_email = access_token.email
    ua.decision_comment = comment
    ua.decision_at = datetime.now(timezone.utc)
    access_token.used = True

    recalculated = []
    if ua.status == "approved":
        recalculated = _recompute_due_dates_for_audit(db, audit)

    db.commit()
    _notify_auditor_unavailability_decision(db, audit, ua)
    _notify_auditees_unavailability_decision(db, audit, ua)

    return {
        "message": "Leave request approved and due dates updated."
        if ua.status == "approved"
        else "Leave request rejected. Due dates unchanged.",
        "audit_id": audit.id,
        "audit_number": audit.audit_number,
        "unavailability_id": ua.id,
        "status": ua.status,
        "cars_affected": len(recalculated),
        "details": recalculated,
    }


def get_audit_from_unavailability_token(db: Session, token: str) -> Audit:
    """Validate an unavailability token and return the related Audit."""
    access_token = get_unavailability_access_token(db, token)

    audit = db.query(Audit).filter_by(id=access_token.audit_id).first()
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    return audit


def get_unavailability_access_token(db: Session, token: str):
    access_token = (
        db.query(AuditUnavailabilityAccessToken).filter_by(token=token).first()
    )
    if not access_token:
        raise HTTPException(status_code=404, detail="Invalid token")

    expires_at = ensure_aware_utc(access_token.expires_at)
    if expires_at and expires_at < utc_now():
        raise HTTPException(status_code=410, detail="Token expired")

    return access_token


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _to_date_pairs(
    unavailabilities: list,
) -> list[Tuple[date, date]]:
    return [
        (
            u.start_date.date() if isinstance(u.start_date, datetime) else u.start_date,
            u.end_date.date() if isinstance(u.end_date, datetime) else u.end_date,
        )
        for u in unavailabilities
    ]


def generate_unavailability_token(
    audit_id: int, 
    email: str, 
    db: Session, 
    unavailability_id: Optional[int] = None,
    expires_hours: int = 720,
    auto_commit: bool = True,
) -> str:
    """Generate unavailability token (30 days validity)."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=expires_hours)

    access_token = AuditUnavailabilityAccessToken(
        audit_id=audit_id,
        unavailability_id=unavailability_id,
        email=email,
        token=token,
        expires_at=expires_at,
        used=False
    )
    db.add(access_token)
    if auto_commit:
        db.commit()
        db.refresh(access_token)
    else:
        db.flush()
    return access_token.token


def get_or_create_unavailability_form_token(
    *,
    db: Session,
    audit_id: int,
    email: str,
    expires_hours: int = 24 * 30,
) -> str:
    """
    Return a reusable unavailability token for auditee form access.
    Tokens linked to a specific PM decision request (unavailability_id != null)
    are excluded.
    """
    now = utc_now()
    existing = (
        db.query(AuditUnavailabilityAccessToken)
        .filter(
            AuditUnavailabilityAccessToken.audit_id == audit_id,
            AuditUnavailabilityAccessToken.email == email,
            AuditUnavailabilityAccessToken.unavailability_id.is_(None),
            AuditUnavailabilityAccessToken.expires_at > now,
        )
        .order_by(AuditUnavailabilityAccessToken.id.desc())
        .first()
    )
    if existing:
        return existing.token

    return generate_unavailability_token(
        audit_id=audit_id,
        email=email,
        db=db,
        unavailability_id=None,
        expires_hours=expires_hours,
    )


# ---------------------------------------------------------------------------
# Resend CAR notifications
# ---------------------------------------------------------------------------

async def resend_car_notifications_for_audit(
    audit_id: int,
    db: Session,
    only_pending: bool = True,
) -> dict:
    """
    Rebuild and re-send the CAR notification email (same layout as report execution)
    for every auditee that has corrective actions on this audit.

    Use this to recover CARs whose auditee was fixed after the fact, or when the
    original notification was never delivered. CARs without an auditee are skipped
    and reported back so they can be assigned first.
    """
    audit = db.query(Audit).filter_by(id=audit_id).first()
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    cars = (
        db.query(CorrectiveAction)
        .options(
            joinedload(CorrectiveAction.answer).joinedload(AuditAnswer.question),
            joinedload(CorrectiveAction.auditee),
        )
        .filter(CorrectiveAction.audit_id == audit_id)
        .all()
    )

    cars_by_auditee: dict[str, list[dict]] = {}
    skipped_no_auditee: list[int] = []

    for car in cars:
        if only_pending and not is_car_editable(car):
            continue
        if not car.auditee or not car.auditee.email:
            skipped_no_auditee.append(car.id)
            continue

        email = car.auditee.email.strip()
        answer = car.answer
        classification = getattr(answer, "classification", None) if answer else None
        if classification:
            car_type = classification
            process = getattr(answer, "process", None) or "N/A"
            paragraph = getattr(answer, "standard_paragraph", None) or "N/A"
            question_text = f"NC {process} - {paragraph}"
        elif car.answer_requirement is not None:
            # VDA requirement CAR: the parent answer may have passed (10), so
            # type and label come from the requirement itself.
            req = car.answer_requirement
            question = getattr(answer, "question", None)
            critical = getattr(question, "critical_value", None) or 6
            car_type = (
                "Critical"
                if req.value is not None and req.value < critical
                else "Improvement"
            )
            q_req = req.question_requirement
            req_label = (q_req.description or "") if q_req else ""
            if q_req and q_req.requirement_code:
                req_label = f"{q_req.requirement_code}: {req_label}"
            question_code = getattr(question, "question_code", None)
            question_text = " - ".join(p for p in (question_code, req_label) if p) or "N/A"
        else:
            car_type = "Critical" if (answer and answer.fail) else "Improvement"
            question_text = (
                getattr(getattr(answer, "question", None), "description", None) or "N/A"
            )

        token = get_or_create_car_token(db, car)
        cars_by_auditee.setdefault(email, []).append(
            {
                "car_id": car.id,
                "type": car_type,
                "question": question_text,
                "finding": car.finding or (answer.finding_text if answer else None) or "N/A",
                "reason": car.reason_why or "",
                "due_date": car.due_date,
                "form_url": build_car_form_url(token),
                "immediate_action_required": bool(car.immediate_action_required),
                "submission_due_at": car.submission_due_at,
                "closure_due_at": car.closure_due_at,
            }
        )

    emails_sent: list[dict] = []
    errors: dict[str, str] = {}

    for email, auditee_cars in cars_by_auditee.items():
        try:
            unavailability_token = get_or_create_unavailability_form_token(
                db=db,
                audit_id=audit_id,
                email=email,
            )
            body_html = build_car_email_body(
                auditee_name=email.split("@")[0],
                audit_reference=audit.audit_number,
                cars=auditee_cars,
                unavailability_url=build_unavailability_url(unavailability_token),
            )
            await send_email(
                subject="Actions Correctives à traiter - Northwind",
                recipients=[email],
                db=db,
                context="car_resend",
                body_html=body_html,
            )
            emails_sent.append({"email": email, "car_count": len(auditee_cars)})
        except Exception as exc:
            logger.exception(
                "CAR resend failed for audit %s auditee %s", audit_id, email
            )
            errors[email] = str(exc)

    return {
        "audit_id": audit_id,
        "audit_number": audit.audit_number,
        "emails_sent": emails_sent,
        "errors": errors,
        "skipped_cars_without_auditee": skipped_no_auditee,
    }
