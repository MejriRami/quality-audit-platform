# app/routers/car_admin.py

import json
from datetime import datetime, date, timedelta
from typing import Optional, List, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session, aliased

from app.config.database import get_db
from app.models.correctiveActionEmailOTP import CorrectiveActionEmailOTP
from app.models.document import Document
from app.services.auth_service import get_current_user
from app.models import (
    CorrectiveAction,
    CarEscalation,
    CorrectiveActionHistory,
    Audit,
    AuditAuditee,
    AuditAnswer,
    Question,
    User,
)
from app.models.CarUnavailability import AuditUnavailability
from app.models.auditor_holiday import AuditorHoliday
from app.utils.due_date import compute_due_date, is_working_day
from app.utils.send_car_email import (
    build_auditee_portal_url,
    build_car_form_url,
    build_unavailability_url,
    generate_car_token,
    send_email,
)
from app.services.blob_storage_service import get_blob_sas_url, get_fresh_doc_url
from app.services.car_service import _extract_blob_name
from app.services.car_service import get_or_create_unavailability_form_token
from app.services.car_service import resend_car_notifications_for_audit
from app.services.car_service import reassign_car_by_auditor
from app.services.role_access_service import has_auditor_role
import logging

logger = logging.getLogger(__name__)


# ---------------------------
# Helpers
# ---------------------------
# ---------------------------
# Schemas
# ---------------------------
class DocumentItem(BaseModel):
    id: int
    filename: str
    file_url: str
    size: int
    uploaded_at: Optional[str] = None
    document_type: Literal["finding_evidence", "car_solution"] = "car_solution"

    class Config:
        from_attributes = True


def normalize_enum(value) -> str:
    """
    Normalize any enum/string coming from SQLAlchemy / DB.
    Handles:
      - "submitted"
      - "SUBMITTED"
      - "ca_status.submitted"
      - "CaStatus.SUBMITTED"
    Returns: lowercase "submitted"
    """
    s = str(value).strip()
    if "." in s:
        s = s.split(".")[-1]
    return s.strip().lower()


def require_auditor(user: User):
    if not has_auditor_role(user):
        raise HTTPException(
            status_code=403,
            detail="You are not auditor. Only auditors can perform this action.",
        )
    return user


def _is_auditor(user: Optional[User]) -> bool:
    return bool(user and has_auditor_role(user))


def _car_escalation_email_is_integer(db: Session) -> bool:
    """
    Backward-compat: some environments still have car_escalations.email_sent_to as INTEGER.
    """
    row = db.execute(
        text(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'car_escalations'
              AND column_name = 'email_sent_to'
            """
        )
    ).first()
    return bool(row and str(row[0]).lower() in {"integer", "bigint", "smallint"})


def _normalize_car_escalation_email_value(
    db: Session, email: Optional[str]
) -> Optional[str | int]:
    if not email:
        return None
    if not _car_escalation_email_is_integer(db):
        return email

    # Old schema expects users.id; fallback to NULL when email is external.
    user = db.query(User.id).filter(func.lower(User.email) == email.lower()).first()
    return int(user[0]) if user else None


def _filter_finding_evidence_documents(
    documents: List[DocumentItem],
) -> List[DocumentItem]:
    return [doc for doc in documents if doc.document_type != "finding_evidence"]


def _apply_non_auditor_visibility(
    item: "CorrectiveActionItem",
) -> "CorrectiveActionItem":
    item.finding_text = None
    item.documents = _filter_finding_evidence_documents(item.documents)
    item.documents_count = len(item.documents)
    return item


def _get_fresh_doc_url(file_url: str) -> str:
    return get_fresh_doc_url(file_url, expiry_days=7)


def _map_escalation_event(code: Optional[str]) -> tuple[str, str, str]:
    normalized = (code or "").strip().upper()
    mapping = {
        "DAY_9_AUDITEE_REMINDER": (
            "reminder",
            "Overdue reminder sent to auditee",
            "info",
        ),
        "DAY_10_AUDITEE_REMINDER": ("reminder", "Second overdue reminder sent to auditee", "info"),
        "DAY_11_PLANT_MANAGER": (
            "escalation",
            "Escalation sent to plant manager",
            "warning",
        ),
        "DAY_11_PM_ESCALATION": (
            "escalation",
            "Escalation sent to plant manager",
            "warning",
        ),
        "DAY_15_GROUP_VP": ("escalation", "Escalation sent to Group VP", "critical"),
        "DAY_11_PLANT_MANAGER": ("escalation", "Escalation sent to plant manager", "warning"),
        "DAY_15_GROUP_VP_ESCALATION": (
            "escalation",
            "Escalation sent to Group VP",
            "critical",
        ),
        "DAY_15_GROUP_VP": ("escalation", "Escalation sent to Group VP", "critical"),
    }
    if normalized.startswith("DUE_DATE_REJECT_RESET"):
        return ("due_date_change", "Due date reset after rejection", "warning")
    if normalized.startswith("DUE_DATE_RECOMPUTED_LEAVE_APPROVED"):
        return ("due_date_change", "Due date recalculated after leave approval", "info")
    if normalized.startswith("DUE_DATE_MANUAL_EXTENDED"):
        return ("due_date_change", "Due date extended manually", "info")
    if normalized.startswith("MANUAL_ESCALATION"):
        return ("manual_escalation", "Manual escalation sent", "warning")
    return mapping.get(normalized, ("event", code or "Event", "info"))


def _build_auditor_sender(user: User) -> dict[str, Optional[str]]:
    sender_name = " ".join(
        part for part in [user.first_name, user.last_name] if part
    ).strip()
    return {
        "sender_email": user.email,
        "sender_name": sender_name or user.email,
        "reply_to": user.email,
    }


def _resolve_audit_sender(
    audit: Optional[Audit],
    fallback_user: User,
) -> dict[str, Optional[str]]:
    audit_auditor = getattr(audit, "auditor", None) if audit else None
    if audit_auditor and audit_auditor.email:
        return _build_auditor_sender(audit_auditor)
    return _build_auditor_sender(fallback_user)


def _encode_activity_comment(prefix: str, **parts: Optional[str]) -> str:
    encoded = [prefix]
    for key, value in parts.items():
        if value is None:
            continue
        safe_value = str(value).replace("|", "/").replace("\n", " ").strip()
        encoded.append(f"{key}={safe_value}")
    return "|".join(encoded)


def _parse_activity_comment(comment: Optional[str]) -> tuple[str, Optional[str]]:
    raw = (comment or "").strip()
    if not raw or "|" not in raw:
        return raw, raw or None

    prefix, *parts = raw.split("|")
    details = []
    for part in parts:
        if "=" not in part:
            details.append(part)
            continue
        key, value = part.split("=", 1)
        details.append(f"{key.replace('_', ' ').title()}: {value}")
    return prefix, "; ".join(details) if details else None


def _load_related_documents(
    db: Session,
    *,
    corrective_action_id: int,
    audit_answer_id: Optional[int],
    audit_id: Optional[int] = None,
    reason_why: Optional[str] = None,
) -> List[DocumentItem]:
    """
    Return merged document list for a CAR:
    - docs uploaded directly to the corrective action
    - docs attached on the source audit answer (finding evidence)
    """
    resolved_audit_answer_id = audit_answer_id
    if resolved_audit_answer_id is None and audit_id is not None and reason_why:
        reason_text = reason_why.strip()
        if reason_text:
            candidate_ids = (
                db.query(AuditAnswer.id)
                .filter(
                    AuditAnswer.audit_id == audit_id,
                    func.lower(func.trim(AuditAnswer.finding_text))
                    == reason_text.lower(),
                )
                .limit(2)
                .all()
            )
            if len(candidate_ids) == 1:
                resolved_audit_answer_id = candidate_ids[0][0]

    filters = [Document.corrective_action_id == corrective_action_id]
    if resolved_audit_answer_id is not None:
        filters.append(Document.audit_answer_id == resolved_audit_answer_id)

    rows = (
        db.query(Document)
        .filter(or_(*filters))
        .order_by(Document.uploaded_at.desc().nullslast(), Document.id.desc())
        .all()
    )

    dedup: dict[int, Document] = {}
    for doc in rows:
        if doc.id not in dedup:
            dedup[doc.id] = doc

    items: List[DocumentItem] = []
    for d in dedup.values():
        is_finding_evidence = bool(d.audit_answer_id) and (
            resolved_audit_answer_id is None
            or d.audit_answer_id == resolved_audit_answer_id
        )
        items.append(
            DocumentItem(
                id=d.id,
                filename=d.filename or f"file-{d.id}",
                file_url=_get_fresh_doc_url(d.file_url),
                size=int(d.size or 0),
                uploaded_at=(
                    d.uploaded_at.strftime("%d/%m/%Y %H:%M") if d.uploaded_at else None
                ),
                document_type="finding_evidence"
                if is_finding_evidence
                else "car_solution",
            )
        )
    return items


router = APIRouter(prefix="/car/admin", tags=["cars-admin"])


class CorrectiveActionItem(BaseModel):
    id: int
    auditId: int

    identifier: Optional[str] = None
    audit_reference: Optional[str] = None
    review_comment: Optional[str] = None

    # "corrective" (root-cause fix) or "immediate" (containment action) -- a
    # finding with immediate_action_required split into two linked rows.
    action_type: Optional[str] = None
    linked_action_id: Optional[int] = None

    auditAnswerId: Optional[int] = None
    finding_type: Optional[str] = None
    corrective_action: Optional[str] = None  # question description
    finding_text: Optional[str] = None  # AuditAnswer.finding_text  ← NEW

    # AuditAnswer fields  ← NEW
    process: Optional[str] = None
    standard_paragraph: Optional[str] = None
    classification: Optional[str] = None

    # Question fields  ← NEW
    chapter: Optional[str] = None

    auditee: str
    pilotUser: Optional[str] = None

    reason_why: Optional[str] = None
    root_cause: Optional[str] = None  # ← NEW
    implemented_solution: Optional[str] = None  # ← NEW

    due_date: Optional[str] = None
    submission_due_at: Optional[str] = None
    closure_due_at: Optional[str] = None
    immediate_action_required: bool = False
    submitted_at: Optional[str] = None  # ← NEW
    created_at: Optional[str] = None  # ← NEW
    plant_name: Optional[str] = None
    status: str
    escalated: bool
    documents: List[DocumentItem] = []
    documents_count: int = 0
    reassigned_from_email: Optional[str] = None
    cc_emails: List[str] = []
    submitted_by_email: Optional[str] = None  # ← NEW
    submission_channel: Optional[str] = None  # ← NEW

    class Config:
        from_attributes = True


class CorrectiveActionListResponse(BaseModel):
    items: List[CorrectiveActionItem]
    total: int
    limit: int
    offset: int
    has_next: bool
    has_prev: bool


class ReviewRequest(BaseModel):
    decision: str  # "ACCEPT" or "REJECT"
    comment: Optional[str] = None


class ExtendDueDateRequest(BaseModel):
    new_due_date: date
    comment: Optional[str] = None


class ManualEscalationRequest(BaseModel):
    emails: List[EmailStr]
    comment: Optional[str] = None


class ReassignAuditeeRequest(BaseModel):
    new_auditee_email: EmailStr
    reason: Optional[str] = None


def _parse_cc_list(raw: Optional[str]) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(e).strip().lower() for e in parsed if str(e).strip()]
    except Exception:
        pass
    return []


def _normalize_emails(emails: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for email in emails:
        value = str(email).strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


class CorrectiveActionReviewHistoryItem(BaseModel):
    id: int
    decision: str
    comment: Optional[str] = None
    reviewed_at: Optional[str] = None
    auditor: Optional[str] = None


class CorrectiveActionActivityItem(BaseModel):
    id: str
    event_type: str
    event_label: str
    at: Optional[str] = None
    actor: Optional[str] = None
    details: Optional[str] = None
    severity: Optional[str] = None


class CorrectiveActionDetailResponse(BaseModel):
    id: int
    auditId: int
    audit_reference: Optional[str] = None
    action_type: Optional[str] = None
    linked_action_id: Optional[int] = None
    auditAnswerId: Optional[int] = None
    finding_type: Optional[str] = None
    corrective_action: Optional[str] = None
    auditee: str
    pilotUser: Optional[str] = None
    reason_why: Optional[str] = None
    due_date: Optional[str] = None
    submission_due_at: Optional[str] = None
    closure_due_at: Optional[str] = None
    immediate_action_required: bool = False
    status: str
    escalated: bool
    root_cause: Optional[str] = None
    implemented_solution: Optional[str] = None
    submitted_at: Optional[str] = None
    created_at: Optional[str] = None
    documents: List[DocumentItem] = []
    review_history: List[CorrectiveActionReviewHistoryItem] = []
    activity_timeline: List[CorrectiveActionActivityItem] = []
    reassigned_from_email: Optional[str] = None
    cc_emails: List[str] = []
    submitted_by_email: Optional[str] = None
    submission_channel: Optional[str] = None


# ---------------------------
# DB ENUM VALUES (from your DB)
# ca_status: pending, submitted, accepted, rejected, closed
# ca_decision: accepted, rejected
# audit_status: planned, ..., completed, ...
# ---------------------------
DB_STATUS_PENDING = "pending"
DB_STATUS_SUBMITTED = "submitted"
DB_STATUS_ACCEPTED = "accepted"
DB_STATUS_REJECTED = "rejected"
DB_STATUS_CLOSED = "closed"

DB_DECISION_ACCEPTED = "accepted"
DB_DECISION_REJECTED = "rejected"

AUDIT_STATUS_COMPLETED = "completed"


def db_status_to_ui(status: str) -> str:
    s = normalize_enum(status)
    mapping = {
        "pending": "Pending",
        "submitted": "Submitted",
        "accepted": "Accepted",
        "rejected": "Rejected",
        "closed": "Completed",
    }
    return mapping.get(s, s.title())


def _get_fresh_doc_url(file_url: str) -> str:
    """Extract blob name from stored URL and generate a fresh 7-day SAS URL."""
    blob_name = _extract_blob_name(file_url)
    if not blob_name:
        return file_url  # fallback to stored URL
    try:
        return get_blob_sas_url(blob_name, expiry_days=7)
    except Exception:
        return file_url  # never break the UI


def maybe_complete_audit_if_all_cars_accepted(db: Session, audit_id: int) -> None:
    """
    If all CARs of an audit are accepted => audit.status becomes 'completed'
    (enum-safe: audit_status_enum has 'completed')
    Migrated Monday CARs are 'closed' rather than 'accepted'; both count as done.
    """
    audit = db.query(Audit).filter(Audit.id == audit_id).first()
    if not audit:
        return

    cars = (
        db.query(CorrectiveAction).filter(CorrectiveAction.audit_id == audit_id).all()
    )
    if not cars:
        return

    all_accepted = all(
        normalize_enum(c.status) in (DB_STATUS_ACCEPTED, DB_STATUS_CLOSED) for c in cars
    )
    if not all_accepted:
        return

    audit.status = AUDIT_STATUS_COMPLETED
    db.add(audit)
    db.commit()


# ---------------------------
# Routes
# ---------------------------


# The audit's second auditor (Audit.second_auditor_id); `User` itself is the
# lead auditor in the CAR queries below.
SecondAuditor = aliased(User, name="second_auditor")


def _pilot_label(row) -> Optional[str]:
    """"Pilot / Auditor" column: lead auditor, plus the second one if any."""
    emails = [e for e in (row.auditor_email, row.second_auditor_email) if e]
    return " & ".join(dict.fromkeys(emails)) or None


def apply_corrective_action_filters(
    q,
    audit_id: Optional[int] = None,
    car_id: Optional[int] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
):
    if audit_id is not None:
        q = q.filter(CorrectiveAction.audit_id == audit_id)

    if car_id is not None:
        q = q.filter(CorrectiveAction.id == car_id)

    if status:
        q = q.filter(CorrectiveAction.status == normalize_enum(status))

    if search:
        term = f"%{search.strip()}%"
        q = q.filter(
            Audit.audit_number.ilike(term)
            | AuditAuditee.email.ilike(term)
            | User.email.ilike(term)
            | SecondAuditor.email.ilike(term)
            | Question.description.ilike(term)
        )

    return q


@router.get("/corrective-actions", response_model=CorrectiveActionListResponse)
def list_corrective_actions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    audit_id: Optional[int] = Query(default=None),
    car_id: Optional[int] = Query(default=None),
    status: Optional[str] = Query(default=None),
    search: Optional[str] = Query(default=None),
    include_documents: bool = Query(default=True),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    user_is_auditor = _is_auditor(current_user)

    # ── latest history subquery (unchanged) ──
    latest_history_subq = (
        db.query(
            CorrectiveActionHistory.corrective_action_id.label("car_id"),
            func.max(CorrectiveActionHistory.id).label("latest_history_id"),
        )
        .group_by(CorrectiveActionHistory.corrective_action_id)
        .subquery()
    )
    LatestHistory = aliased(CorrectiveActionHistory)

    base_q = (
        db.query(
            CorrectiveAction.id.label("id"),
            CorrectiveAction.audit_id.label("audit_id"),
            CorrectiveAction.identifier.label("identifier"),  # ← NEW
            CorrectiveAction.action_type.label("action_type"),
            CorrectiveAction.linked_action_id.label("linked_action_id"),
            Audit.audit_number.label("audit_reference"),
            Audit.plant.label("plant_name"),  # ← NEW
            CorrectiveAction.audit_answer_id.label("audit_answer_id"),
            CorrectiveAction.reason_why.label("reason_why"),
            CorrectiveAction.root_cause.label("root_cause"),  # ← NEW
            CorrectiveAction.finding.label("migrated_finding"),
            CorrectiveAction.migrated_question_text.label("migrated_question_text"),
            CorrectiveAction.implemented_solution.label(
                "implemented_solution"
            ),  # ← NEW
            CorrectiveAction.due_date.label("due_date"),
            CorrectiveAction.submission_due_at.label("submission_due_at"),
            CorrectiveAction.closure_due_at.label("closure_due_at"),
            CorrectiveAction.immediate_action_required.label("immediate_action_required"),
            CorrectiveAction.status.label("status"),
            CorrectiveAction.escalated.label("escalated"),
            CorrectiveAction.created_at.label("created_at"),
            CorrectiveAction.submitted_at.label("submitted_at"),  # ← NEW
            CorrectiveAction.reassigned_from_email.label("reassigned_from_email"),
            CorrectiveAction.cc_emails.label("cc_emails_raw"),
            CorrectiveAction.submitted_by_email.label("submitted_by_email"),  # ← NEW
            CorrectiveAction.submission_channel.label("submission_channel"),  # ← NEW
            AuditAuditee.email.label("auditee_email"),
            User.email.label("auditor_email"),
            SecondAuditor.email.label("second_auditor_email"),
            Question.description.label("question_description"),
            Question.chapter.label("chapter"),  # ← NEW
            AuditAnswer.fail.label("fail"),
            AuditAnswer.improve.label("improve"),
            AuditAnswer.pass_.label("pass_flag"),
            AuditAnswer.finding_text.label("finding_text"),  # ← NEW
            AuditAnswer.process.label("process"),  # ← NEW
            AuditAnswer.standard_paragraph.label("standard_paragraph"),  # ← NEW
            AuditAnswer.classification.label("classification"),  # ← NEW
            LatestHistory.comment.label("review_comment"),
        )
        .join(Audit, Audit.id == CorrectiveAction.audit_id)
        .outerjoin(AuditAuditee, AuditAuditee.id == CorrectiveAction.auditee_id)
        .outerjoin(AuditAnswer, AuditAnswer.id == CorrectiveAction.audit_answer_id)
        .outerjoin(Question, Question.id == AuditAnswer.question_id)
        .outerjoin(User, User.id == Audit.auditor_id)
        .outerjoin(SecondAuditor, SecondAuditor.id == Audit.second_auditor_id)
        .outerjoin(
            latest_history_subq,
            latest_history_subq.c.car_id == CorrectiveAction.id,
        )
        .outerjoin(
            LatestHistory,
            LatestHistory.id == latest_history_subq.c.latest_history_id,
        )
    )

    base_q = apply_corrective_action_filters(
        base_q, audit_id=audit_id, car_id=car_id, status=status, search=search
    )

    # ── count query (unchanged logic) ──
    total_q = (
        db.query(func.count(CorrectiveAction.id))
        .join(Audit, Audit.id == CorrectiveAction.audit_id)
        .outerjoin(AuditAuditee, AuditAuditee.id == CorrectiveAction.auditee_id)
        .outerjoin(AuditAnswer, AuditAnswer.id == CorrectiveAction.audit_answer_id)
        .outerjoin(Question, Question.id == AuditAnswer.question_id)
        .outerjoin(User, User.id == Audit.auditor_id)
        .outerjoin(SecondAuditor, SecondAuditor.id == Audit.second_auditor_id)
    )
    total_q = apply_corrective_action_filters(
        total_q, audit_id=audit_id, car_id=car_id, status=status, search=search
    )
    total_count = total_q.scalar() or 0

    rows = (
        base_q.order_by(
            CorrectiveAction.created_at.desc().nullslast(),
            CorrectiveAction.id.desc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )

    # ── Build items ──
    row_car_ids = [r.id for r in rows]
    row_answer_ids = [r.audit_answer_id for r in rows if r.audit_answer_id is not None]
    car_doc_counts: dict[int, int] = {}
    answer_doc_counts: dict[int, int] = {}
    if row_car_ids:
        for doc_row in (
            db.query(Document.corrective_action_id, func.count(Document.id))
            .filter(Document.corrective_action_id.in_(row_car_ids))
            .group_by(Document.corrective_action_id)
            .all()
        ):
            if doc_row[0] is not None:
                car_doc_counts[int(doc_row[0])] = int(doc_row[1] or 0)
    if row_answer_ids:
        for doc_row in (
            db.query(Document.audit_answer_id, func.count(Document.id))
            .filter(Document.audit_answer_id.in_(row_answer_ids))
            .group_by(Document.audit_answer_id)
            .all()
        ):
            if doc_row[0] is not None:
                answer_doc_counts[int(doc_row[0])] = int(doc_row[1] or 0)

    items: List[CorrectiveActionItem] = []
    for row in rows:
        finding_type = None
        if row.fail:
            finding_type = "FAIL"
        elif row.improve:
            finding_type = "IMPROVE"
        elif row.pass_flag:
            finding_type = "PASS"

        items.append(
            CorrectiveActionItem(
                id=row.id,
                auditId=row.audit_id,
                identifier=row.identifier,
                action_type=row.action_type,
                linked_action_id=row.linked_action_id,
                auditAnswerId=row.audit_answer_id,
                plant_name=row.plant_name,
                audit_reference=row.audit_reference or "",
                finding_type=finding_type,
                # Question.description covers app-native CARs; migrated CARs
                # have no AuditAnswer/Question, so fall back to the finding
                # text backfilled from the Monday.com migration. This is the
                # "Question / Action" column in the CAR table.
                corrective_action=row.question_description or row.migrated_question_text or row.migrated_finding,
                finding_text=row.migrated_finding or row.finding_text,
                process=row.process,
                standard_paragraph=row.standard_paragraph,
                classification=row.classification,
                chapter=row.chapter,
                auditee=row.auditee_email or "",
                pilotUser=_pilot_label(row),
                reason_why=row.reason_why,
                root_cause=row.root_cause,
                implemented_solution=row.implemented_solution,
                reassigned_from_email=row.reassigned_from_email,
                cc_emails=_parse_cc_list(row.cc_emails_raw),
                submitted_by_email=row.submitted_by_email,
                submission_channel=row.submission_channel,
                due_date=row.due_date.isoformat() if row.due_date else None,
                submission_due_at=row.submission_due_at.isoformat() if row.submission_due_at else None,
                closure_due_at=row.closure_due_at.isoformat() if row.closure_due_at else None,
                immediate_action_required=bool(row.immediate_action_required),
                submitted_at=(
                    row.submitted_at.strftime("%d/%m/%Y %H:%M")
                    if row.submitted_at
                    else None
                ),
                created_at=(
                    row.created_at.strftime("%d/%m/%Y %H:%M")
                    if row.created_at
                    else None
                ),
                status=db_status_to_ui(row.status),
                escalated=bool(row.escalated),
                # send review_comment for all statuses; front-end filters
                review_comment=row.review_comment,
                documents_count=(
                    car_doc_counts.get(row.id, 0)
                    + (
                        answer_doc_counts.get(row.audit_answer_id, 0)
                        if user_is_auditor
                        else 0
                    )
                ),
            )
        )

    if include_documents:
        # Attach both CAR and finding documents only when explicitly requested.
        for item in items:
            item.documents = _load_related_documents(
                db,
                corrective_action_id=item.id,
                audit_answer_id=item.auditAnswerId,
                audit_id=item.auditId,
                reason_why=item.reason_why,
            )
            if not user_is_auditor:
                _apply_non_auditor_visibility(item)
    elif not user_is_auditor:
        for item in items:
            item.finding_text = None

    return CorrectiveActionListResponse(
        items=items,
        total=total_count,
        limit=limit,
        offset=offset,
        has_next=(offset + limit) < total_count,
        has_prev=offset > 0,
    )


# ---------------------------------------------------------------------------
# Auditor "on holiday" — pauses CAR escalation for that auditor's own audits
# (must be registered before the generic "/{car_id}" route below, or FastAPI
# will match "/auditor-holidays" as a car_id path parameter instead)
# ---------------------------------------------------------------------------

class AuditorHolidayCreate(BaseModel):
    start_date: date
    end_date: date
    reason: Optional[str] = None


class AuditorHolidayItem(BaseModel):
    id: int
    start_date: str
    end_date: str
    reason: Optional[str] = None


def _to_holiday_item(row: AuditorHoliday) -> AuditorHolidayItem:
    return AuditorHolidayItem(
        id=row.id,
        start_date=row.start_date.isoformat(),
        end_date=row.end_date.isoformat(),
        reason=row.reason,
    )


@router.get("/auditor-holidays", response_model=List[AuditorHolidayItem])
def list_my_auditor_holidays(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_auditor(current_user)
    rows = (
        db.query(AuditorHoliday)
        .filter(AuditorHoliday.user_id == current_user.id)
        .order_by(AuditorHoliday.start_date.desc())
        .all()
    )
    return [_to_holiday_item(r) for r in rows]


@router.post("/auditor-holidays", response_model=AuditorHolidayItem)
def create_my_auditor_holiday(
    payload: AuditorHolidayCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_auditor(current_user)
    if payload.end_date < payload.start_date:
        raise HTTPException(
            status_code=400, detail="End date must be on or after start date."
        )
    row = AuditorHoliday(
        user_id=current_user.id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        reason=payload.reason,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_holiday_item(row)


@router.delete("/auditor-holidays/{holiday_id}")
def delete_my_auditor_holiday(
    holiday_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_auditor(current_user)
    row = (
        db.query(AuditorHoliday)
        .filter(
            AuditorHoliday.id == holiday_id,
            AuditorHoliday.user_id == current_user.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Holiday period not found.")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/{car_id}", response_model=CorrectiveActionDetailResponse)
def get_corrective_action_details(
    car_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_is_auditor = _is_auditor(current_user)

    row = (
        db.query(
            CorrectiveAction.id.label("id"),
            CorrectiveAction.audit_id.label("audit_id"),
            Audit.audit_number.label("audit_reference"),
            CorrectiveAction.action_type.label("action_type"),
            CorrectiveAction.linked_action_id.label("linked_action_id"),
            CorrectiveAction.audit_answer_id.label("audit_answer_id"),
            CorrectiveAction.reason_why.label("reason_why"),
            CorrectiveAction.due_date.label("due_date"),
            CorrectiveAction.submission_due_at.label("submission_due_at"),
            CorrectiveAction.closure_due_at.label("closure_due_at"),
            CorrectiveAction.immediate_action_required.label("immediate_action_required"),
            CorrectiveAction.status.label("status"),
            CorrectiveAction.escalated.label("escalated"),
            CorrectiveAction.finding.label("migrated_finding"),
            CorrectiveAction.migrated_question_text.label("migrated_question_text"),
            CorrectiveAction.root_cause.label("root_cause"),
            CorrectiveAction.implemented_solution.label("implemented_solution"),
            CorrectiveAction.submitted_at.label("submitted_at"),
            CorrectiveAction.created_at.label("created_at"),
            CorrectiveAction.reassigned_from_email.label("reassigned_from_email"),
            CorrectiveAction.cc_emails.label("cc_emails_raw"),
            CorrectiveAction.submitted_by_email.label("submitted_by_email"),
            CorrectiveAction.submission_channel.label("submission_channel"),
            AuditAuditee.email.label("auditee_email"),
            User.email.label("auditor_email"),
            SecondAuditor.email.label("second_auditor_email"),
            Question.description.label("question_description"),
            AuditAnswer.fail.label("fail"),
            AuditAnswer.improve.label("improve"),
            AuditAnswer.pass_.label("pass_flag"),
        )
        .join(Audit, Audit.id == CorrectiveAction.audit_id)
        .outerjoin(AuditAuditee, AuditAuditee.id == CorrectiveAction.auditee_id)
        .outerjoin(AuditAnswer, AuditAnswer.id == CorrectiveAction.audit_answer_id)
        .outerjoin(Question, Question.id == AuditAnswer.question_id)
        .outerjoin(User, User.id == Audit.auditor_id)
        .outerjoin(SecondAuditor, SecondAuditor.id == Audit.second_auditor_id)
        .filter(CorrectiveAction.id == car_id)
        .first()
    )

    if not row:
        raise HTTPException(status_code=404, detail="Corrective action not found")

    finding_type = None
    if row.fail:
        finding_type = "FAIL"
    elif row.improve:
        finding_type = "IMPROVE"
    elif row.pass_flag:
        finding_type = "PASS"

    history_rows = (
        db.query(
            CorrectiveActionHistory.id.label("id"),
            CorrectiveActionHistory.decision.label("decision"),
            CorrectiveActionHistory.comment.label("comment"),
            CorrectiveActionHistory.reviewed_at.label("reviewed_at"),
            User.email.label("auditor_email"),
        )
        .outerjoin(User, User.id == CorrectiveActionHistory.auditor_id)
        .filter(CorrectiveActionHistory.corrective_action_id == car_id)
        .order_by(
            CorrectiveActionHistory.reviewed_at.asc().nullsfirst(),
            CorrectiveActionHistory.id.asc(),
        )
        .all()
    )

    review_history = (
        [
            CorrectiveActionReviewHistoryItem(
                id=h.id,
                decision=normalize_enum(h.decision) if h.decision is not None else "",
                comment=h.comment,
                reviewed_at=h.reviewed_at.isoformat() if h.reviewed_at else None,
                auditor=h.auditor_email,
            )
            for h in history_rows
        ]
        if user_is_auditor
        else []
    )

    documents = _load_related_documents(
        db,
        corrective_action_id=row.id,
        audit_answer_id=row.audit_answer_id,
        audit_id=row.audit_id,
        reason_why=row.reason_why,
    )
    if not user_is_auditor:
        documents = _filter_finding_evidence_documents(documents)

    activity_timeline: List[CorrectiveActionActivityItem] = []
    if user_is_auditor and row.created_at:
        activity_timeline.append(
            CorrectiveActionActivityItem(
                id=f"car-created-{row.id}",
                event_type="car_created",
                event_label="Corrective action created",
                at=row.created_at.isoformat(),
                actor=row.auditor_email,
                details=row.reason_why,
                severity="info",
            )
        )
    if user_is_auditor and row.submitted_at:
        activity_timeline.append(
            CorrectiveActionActivityItem(
                id=f"car-submitted-{row.id}",
                event_type="submission",
                event_label="Auditee submitted corrective action",
                at=row.submitted_at.isoformat(),
                actor=row.auditee_email,
                severity="info",
            )
        )

    if user_is_auditor:
        for h in history_rows:
            if h.reviewed_at is None:
                continue
            decision = (
                normalize_enum(h.decision) if h.decision is not None else "reviewed"
            )
            activity_timeline.append(
                CorrectiveActionActivityItem(
                    id=f"review-{h.id}",
                    event_type="review",
                    event_label=f"Auditor {decision}",
                    at=h.reviewed_at.isoformat(),
                    actor=h.auditor_email,
                    details=h.comment,
                    severity="warning" if decision == "rejected" else "info",
                )
            )

        escalation_rows = (
            db.query(
                CarEscalation.id,
                CarEscalation.escalated_at,
                CarEscalation.email_sent_to,
                CarEscalation.comment,
            )
            .filter(CarEscalation.corrective_action_id == car_id)
            .order_by(
                CarEscalation.escalated_at.asc().nullsfirst(), CarEscalation.id.asc()
            )
            .all()
        )
        for e in escalation_rows:
            raw_code, parsed_details = _parse_activity_comment(e.comment)
            event_type, label, severity = _map_escalation_event(raw_code)
            activity_timeline.append(
                CorrectiveActionActivityItem(
                    id=f"esc-{e.id}",
                    event_type=event_type,
                    event_label=label,
                    at=e.escalated_at.isoformat() if e.escalated_at else None,
                    actor=e.email_sent_to,
                    details=parsed_details,
                    severity=severity,
                )
            )

        if row.audit_id and row.auditee_email:
            leave_rows = (
                db.query(AuditUnavailability)
                .filter(
                    AuditUnavailability.audit_id == row.audit_id,
                    func.lower(AuditUnavailability.requested_by_email)
                    == row.auditee_email.strip().lower(),
                )
                .order_by(
                    AuditUnavailability.created_at.asc().nullsfirst(),
                    AuditUnavailability.id.asc(),
                )
                .all()
            )
            for leave in leave_rows:
                period = f"{leave.start_date.strftime('%d/%m/%Y')} - {leave.end_date.strftime('%d/%m/%Y')}"
                activity_timeline.append(
                    CorrectiveActionActivityItem(
                        id=f"leave-create-{leave.id}",
                        event_type="leave_declaration",
                        event_label="Auditee declared leave",
                        at=leave.created_at.isoformat() if leave.created_at else None,
                        actor=leave.requested_by_email,
                        details=f"{period}. Reason: {leave.reason or 'N/A'}",
                        severity="info",
                    )
                )
                if leave.decision_at:
                    decision = (leave.status or "pending").strip().lower()
                    activity_timeline.append(
                        CorrectiveActionActivityItem(
                            id=f"leave-decision-{leave.id}",
                            event_type="leave_decision",
                            event_label=f"Leave request {decision}",
                            at=leave.decision_at.isoformat(),
                            actor=leave.decision_by_email,
                            details=leave.decision_comment,
                            severity="info" if decision == "approved" else "warning",
                        )
                    )

        activity_timeline.sort(
            key=lambda ev: (
                ev.at is None,
                ev.at or "",
                ev.id,
            )
        )

    return CorrectiveActionDetailResponse(
        id=row.id,
        auditId=row.audit_id,
        audit_reference=row.audit_reference or "",
        action_type=row.action_type,
        linked_action_id=row.linked_action_id,
        auditAnswerId=row.audit_answer_id,
        finding_type=finding_type,
        # Question.description covers app-native CARs; migrated CARs have no
        # AuditAnswer/Question, so fall back to the finding text backfilled
        # from the Monday.com migration.
        corrective_action=row.question_description or row.migrated_question_text or row.migrated_finding,
        auditee=row.auditee_email or "",
        pilotUser=_pilot_label(row),
        reason_why=row.reason_why,
        due_date=row.due_date.isoformat() if row.due_date else None,
        submission_due_at=row.submission_due_at.isoformat() if row.submission_due_at else None,
        closure_due_at=row.closure_due_at.isoformat() if row.closure_due_at else None,
        immediate_action_required=bool(row.immediate_action_required),
        status=db_status_to_ui(row.status),
        escalated=bool(row.escalated),
        root_cause=row.root_cause,
        implemented_solution=row.implemented_solution,
        submitted_at=row.submitted_at.isoformat() if row.submitted_at else None,
        created_at=row.created_at.isoformat() if row.created_at else None,
        documents=documents,
        review_history=review_history,
        activity_timeline=activity_timeline,
        reassigned_from_email=row.reassigned_from_email,
        cc_emails=_parse_cc_list(row.cc_emails_raw),
        submitted_by_email=row.submitted_by_email,
        submission_channel=row.submission_channel,
    )

    ##TODO update due_date and email design to handle unavailability periods (audit-level) that should pause the countdown of due_date and delay it accordingly, with email notifications to auditee when due_date is approaching and when due_date is updated due to unavailability period addition


@router.post("/{car_id}/review")
async def review_corrective_action(
    car_id: int,
    payload: ReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_auditor(current_user)

    ca = db.query(CorrectiveAction).filter(CorrectiveAction.id == car_id).first()
    if not ca:
        raise HTTPException(status_code=404, detail="Corrective action not found")

    current_status = normalize_enum(ca.status)

    if current_status != DB_STATUS_SUBMITTED:
        raise HTTPException(
            status_code=400,
            detail=f"CAR must be {DB_STATUS_SUBMITTED} to review (current={current_status})",
        )

    decision = payload.decision.upper().strip()
    if decision not in ("ACCEPT", "REJECT"):
        raise HTTPException(status_code=422, detail="decision must be ACCEPT or REJECT")

    if decision == "REJECT" and (not payload.comment or not payload.comment.strip()):
        raise HTTPException(
            status_code=422, detail="comment is required when rejecting"
        )

    audit = ca.audit
    # log auditee email for debugging
    auditee_email = ca.auditee.email if ca.auditee else None
    # Any auditee invited to this audit can act on any of its CARs (see
    # verify_email_for_car), not just the one it happens to be assigned to —
    # so a rejection should reach all of them, not just the assignee.
    all_audit_auditee_emails = sorted({
        (a.email or "").strip().lower()
        for a in (audit.auditees if audit else []) or []
        if getattr(a, "email", None)
    })
    if auditee_email and auditee_email.strip().lower() not in all_audit_auditee_emails:
        all_audit_auditee_emails.append(auditee_email.strip().lower())

    if decision == "ACCEPT":
        ca.status = DB_STATUS_ACCEPTED
        ca.escalated = False
        db_decision = DB_DECISION_ACCEPTED
    else:
        # Reopen for auditee to submit again
        ca.status = DB_STATUS_REJECTED
        ca.escalated = False
        db_decision = DB_DECISION_REJECTED
        db.query(CorrectiveActionEmailOTP).filter(
            CorrectiveActionEmailOTP.corrective_action_id == ca.id
        ).update({"verified": False}, synchronize_session=False)

        # ✅ Set new due date: now + 1 working day (respects holidays)
        #    Your existing cron will escalate if this passes without a submission
        old_due = ca.due_date
        try:
            new_due = compute_due_date(
                created_at=datetime.utcnow(),
                plant=audit.plant.lower() if audit and audit.plant else "default",
                workdays=3,
            )
        except ValueError:
            # No linked audit or unknown plant (e.g. legacy CARs migrated
            # from Monday.com without an audit link) -- fall back to a
            # plain weekend-only due date instead of failing the reject.
            new_due = datetime.utcnow().date()
            added = 0
            while added < 3:
                new_due += timedelta(days=1)
                if is_working_day(new_due, set()):
                    added += 1
        ca.due_date = new_due
        db.add(
            CarEscalation(
                corrective_action_id=ca.id,
                escalated_at=datetime.utcnow(),
                email_sent_to=_normalize_car_escalation_email_value(
                    db, auditee_email
                ),
                comment=(
                    "DUE_DATE_REJECT_RESET"
                    f"|old={(old_due.isoformat() if old_due else 'None')}"
                    f"|new={(new_due.isoformat() if new_due else 'None')}"
                ),
            )
        )

        token = generate_car_token(db, ca)
        form_url = build_car_form_url(token)
        portal_url = build_auditee_portal_url()
        unavailability_token = None
        if audit and auditee_email:
            unavailability_token = get_or_create_unavailability_form_token(
                db=db,
                audit_id=audit.id,
                email=auditee_email,
            )
        unavailability_url = (
            build_unavailability_url(unavailability_token)
            if unavailability_token
            else "#"
        )

        # Pertinent context beyond the bare CAR id: the human-friendly
        # identifier, which framework/process-element this finding sits
        # under, and who reviewed it — the same grounding details the AI
        # Assistant itself is given, so the email and the coaching agree.
        car_reference = ca.identifier or f"CAR-{ca.id}"
        question = ca.answer.question if ca.answer else None
        questionnaire = audit.questionnaire if audit else None
        framework = questionnaire.framework if questionnaire else None
        framework_label = framework.label if framework else None
        element_code = (
            (question.element or "").strip().upper()
            if question and question.element
            else None
        )
        reviewer_name = (
            f"{current_user.first_name} {current_user.last_name}".strip()
            if current_user
            else None
        )
        reviewed_date_str = datetime.utcnow().strftime("%d %b %Y")

        if all_audit_auditee_emails:
            deadline_str = new_due.strftime(
                "%A, %B %d, %Y"
            )  # e.g. "Monday, April 14, 2025"
            logger.info(
                f"Sending CAR rejection email to {all_audit_auditee_emails} "
                f"for CAR {ca.id}, new deadline: {new_due}"
            )
            # NOTE: the "Declare Leave" link below is generated for the CAR's
            # primary auditee_email only — if other invited auditees on this
            # audit click it, it currently submits the leave declaration under
            # the primary auditee's identity, not their own. Fine for now
            # since the link is informational for them, but worth a proper
            # per-recipient token if this becomes a real workflow for them.
            await send_email(
                subject=f"CAR Rejected – Audit {audit.audit_number if audit else ''}",
                recipients=all_audit_auditee_emails,
                cc=_parse_cc_list(ca.cc_emails) or None,
                db=db,
                context="car_rejection",
                **_build_auditor_sender(current_user),
                body_html=f"""
                <div style="max-width:560px;margin:0 auto;font-family:Arial,sans-serif;font-size:14px;color:#1a1a1a;background:#fff;border:1px solid #e5e5e5;border-radius:10px;overflow:hidden;">

                <div style="background:#fff;padding:20px 28px 0;text-align:center;">
                    <img src="https://your-app.azurewebsites.net/assets/northwind-CfOjGbwW.png"
                         alt="Northwind" style="max-height:40px;" />
                </div>

                <div style="background:#A32D2D;padding:18px 28px;margin-top:16px;">
                    <p style="margin:0;font-size:11px;color:#F7C1C1;letter-spacing:0.08em;text-transform:uppercase;">Corrective action report{" &middot; " + car_reference if car_reference else ""}</p>
                    <p style="margin:6px 0 0;font-size:18px;font-weight:600;color:#fff;">Submission rejected</p>
                </div>

                <div style="padding:24px 28px;">
                    <p style="margin:0 0 20px;line-height:1.6;">Your corrective action submission has been reviewed and <b style="color:#A32D2D;">rejected</b>. Please review the details below and resubmit before the deadline.</p>

                    <div style="background:#f7f7f5;border-radius:8px;padding:16px 20px;margin-bottom:20px;">
                    <table style="width:100%;border-collapse:collapse;font-size:13px;">
                        <tr>
                        <td style="color:#666;padding:5px 0;width:40%;">Audit number</td>
                        <td style="font-weight:600;padding:5px 0;">{audit.audit_number if audit else "N/A"}</td>
                        </tr>
                        <tr>
                        <td style="color:#666;padding:5px 0;">Plant</td>
                        <td style="font-weight:600;padding:5px 0;">{audit.plant if audit and audit.plant else "N/A"}</td>
                        </tr>
                        <tr>
                        <td style="color:#666;padding:5px 0;">CAR reference</td>
                        <td style="font-weight:600;padding:5px 0;">{car_reference}</td>
                        </tr>
                        {f'''<tr>
                        <td style="color:#666;padding:5px 0;">Framework</td>
                        <td style="font-weight:600;padding:5px 0;">{framework_label}{f" &middot; {element_code}" if element_code else ""}</td>
                        </tr>''' if framework_label else ""}
                        <tr>
                        <td style="color:#666;padding:5px 0;">Non-conformity</td>
                        <td style="font-weight:600;padding:5px 0;line-height:1.5;">{ca.reason_why or "N/A"}</td>
                        </tr>
                        {f'''<tr>
                        <td style="color:#666;padding:5px 0;">Reviewed by</td>
                        <td style="font-weight:600;padding:5px 0;">{reviewer_name} &middot; {reviewed_date_str}</td>
                        </tr>''' if reviewer_name else ""}
                    </table>
                    </div>

                    <div style="border-left:3px solid #E24B4A;background:#FCEBEB;padding:12px 16px;margin-bottom:20px;">
                    <p style="margin:0 0 4px;font-size:12px;font-weight:600;color:#A32D2D;">Reason for rejection</p>
                    <p style="margin:0;color:#791F1F;line-height:1.6;">{payload.comment}</p>
                    </div>

                    <div style="border:1px solid #F09595;border-radius:8px;background:#FCEBEB;padding:14px 18px;margin-bottom:24px;">
                    <p style="margin:0 0 4px;font-size:13px;font-weight:600;color:#A32D2D;">Resubmission deadline</p>
                    <p style="margin:0;color:#791F1F;font-size:13px;line-height:1.5;">You have <b>3 working day</b> to update and resubmit — by <b>{deadline_str}</b>. Failure to submit by this deadline will trigger an escalation to management.</p>
                    </div>

                    <div style="margin-bottom:12px;">
                      <a href="{form_url}" style="display:inline-block;background:#185FA5;color:#fff;text-align:center;padding:11px 20px;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px;margin:0 10px 10px 0;">Update &amp; resubmit corrective action</a>
                      <a href="{unavailability_url}" style="display:inline-block;background:#6b7280;color:#fff;text-align:center;padding:11px 20px;border-radius:8px;text-decoration:none;font-weight:600;font-size:14px;margin:0 0 10px 0;">Declare Leave</a>
                    </div>

                    <div style="background:#EFF6FF;border:1px solid #BFDBFE;border-radius:8px;padding:14px 18px;margin-bottom:20px;">
                      <p style="margin:0 0 8px;font-size:13px;color:#1e3a5f;line-height:1.5;">Want help understanding what needs to change before resubmitting? The AI Assistant in your portal already knows this CAR was rejected and why — it can walk you through building a resubmission that addresses the auditor's actual comment.</p>
                      <a href="{portal_url}" style="display:inline-block;background:#1B5E20;color:#fff;text-align:center;padding:10px 18px;border-radius:8px;text-decoration:none;font-weight:600;font-size:13px;">Get help in My Portal</a>
                    </div>

                    <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:12px 14px;margin-bottom:24px;">
                      <p style="margin:0 0 8px;font-size:12px;color:#475569;font-weight:600;">If buttons don't open, use these direct links:</p>
                      <p style="margin:0 0 6px;font-size:12px;word-break:break-all;"><span style="color:#64748b;">CAR form:</span> <a href="{form_url}" style="color:#0f4fa8;">{form_url}</a></p>
                      <p style="margin:0 0 6px;font-size:12px;word-break:break-all;"><span style="color:#64748b;">Declare leave:</span> <a href="{unavailability_url}" style="color:#0f4fa8;">{unavailability_url}</a></p>
                      <p style="margin:0;font-size:12px;word-break:break-all;"><span style="color:#64748b;">My Portal:</span> <a href="{portal_url}" style="color:#0f4fa8;">{portal_url}</a></p>
                    </div>

                    <p style="margin:0;font-size:12px;color:#888;line-height:1.6;border-top:1px solid #eee;padding-top:16px;">If you believe this rejection was made in error, please contact your auditor directly. Do not reply to this email.</p>
                </div>

                </div>
                """,
            )

    # ✅ history (enum-safe)
    hist = CorrectiveActionHistory(
        corrective_action_id=ca.id,
        auditor_id=current_user.id,
        decision=db_decision,
        comment=payload.comment,
        reviewed_at=datetime.utcnow(),
        document_id=None,
    )
    db.add(hist)

    db.commit()

    # ✅ if accepted, maybe complete audit
    if decision == "ACCEPT" and audit:
        maybe_complete_audit_if_all_cars_accepted(db, audit.id)

    return {"ok": True, "status": normalize_enum(ca.status)}


# ── Pydantic response schema (add to your schemas file) ──────────────────────
@router.post("/{car_id}/extend-due-date")
async def extend_due_date_manually(
    car_id: int,
    payload: ExtendDueDateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_auditor(current_user)

    ca = db.query(CorrectiveAction).filter(CorrectiveAction.id == car_id).first()
    if not ca:
        raise HTTPException(status_code=404, detail="Corrective action not found")
    if not ca.audit:
        raise HTTPException(
            status_code=400, detail="Corrective action is not linked to an audit"
        )
    if ca.due_date and payload.new_due_date <= ca.due_date:
        raise HTTPException(
            status_code=400,
            detail="New due date must be later than the current due date.",
        )

    old_due = ca.due_date
    ca.due_date = payload.new_due_date
    ca.due_date_base = payload.new_due_date
    ca.escalated = False

    db.add(
        CarEscalation(
            corrective_action_id=ca.id,
            escalated_at=datetime.utcnow(),
            email_sent_to=_normalize_car_escalation_email_value(
                db, current_user.email
            ),
            comment=_encode_activity_comment(
                "DUE_DATE_MANUAL_EXTENDED",
                actor=current_user.email,
                old=old_due.isoformat() if old_due else None,
                new=payload.new_due_date.isoformat(),
                reason=payload.comment,
            ),
        )
    )

    auditee_email = ca.auditee.email if ca.auditee and ca.auditee.email else None
    if auditee_email:
        await send_email(
            subject=f"CAR Due Date Extended - Audit {ca.audit.audit_number}",
            recipients=[auditee_email],
            cc=_parse_cc_list(ca.cc_emails) or None,
            db=db,
            context="car_due_date_extended",
            **_build_auditor_sender(current_user),
            body_html=(
                f"<p>The due date for corrective action <strong>{ca.identifier or f'CAR-{ca.id}'}</strong> has been extended by the auditor.</p>"
                f"<p><strong>Previous due date:</strong> {old_due.isoformat() if old_due else 'N/A'}</p>"
                f"<p><strong>New due date:</strong> {payload.new_due_date.isoformat()}</p>"
                f"<p><strong>Comment:</strong> {payload.comment or 'No comment provided.'}</p>"
            ),
        )

    db.commit()
    return {
        "ok": True,
        "car_id": ca.id,
        "old_due_date": old_due.isoformat() if old_due else None,
        "new_due_date": ca.due_date.isoformat() if ca.due_date else None,
    }


@router.post("/{car_id}/escalate")
async def escalate_car_manually(
    car_id: int,
    payload: ManualEscalationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_auditor(current_user)

    ca = db.query(CorrectiveAction).filter(CorrectiveAction.id == car_id).first()
    if not ca:
        raise HTTPException(status_code=404, detail="Corrective action not found")
    if not ca.audit:
        raise HTTPException(
            status_code=400, detail="Corrective action is not linked to an audit"
        )

    recipients = _normalize_emails(payload.emails)
    if not recipients:
        raise HTTPException(
            status_code=400, detail="At least one escalation email is required."
        )

    body_html = (
        f"<p>The auditor has escalated corrective action <strong>{ca.identifier or f'CAR-{ca.id}'}</strong>.</p>"
        f"<p><strong>Audit:</strong> {ca.audit.audit_number}</p>"
        f"<p><strong>Plant:</strong> {ca.audit.plant}</p>"
        f"<p><strong>Auditee:</strong> {ca.auditee.email if ca.auditee and ca.auditee.email else 'N/A'}</p>"
        f"<p><strong>Due date:</strong> {ca.due_date.isoformat() if ca.due_date else 'N/A'}</p>"
        f"<p><strong>Comment:</strong> {payload.comment or 'No comment provided.'}</p>"
    )

    for recipient in recipients:
        await send_email(
            subject=f"Escalation - CAR {ca.identifier or f'CAR-{ca.id}'}",
            recipients=[recipient],
            cc=_parse_cc_list(ca.cc_emails) or None,
            db=db,
            context="car_manual_escalation",
            **_resolve_audit_sender(ca.audit, current_user),
            body_html=body_html,
        )

    ca.escalated = True
    for recipient in recipients:
        db.add(
            CarEscalation(
                corrective_action_id=ca.id,
                escalated_at=datetime.utcnow(),
                email_sent_to=_normalize_car_escalation_email_value(
                    db, recipient
                ),
                comment=_encode_activity_comment(
                    "MANUAL_ESCALATION",
                    actor=current_user.email,
                    recipient=recipient,
                    comment=payload.comment,
                ),
            )
        )

    db.commit()
    return {"ok": True, "car_id": ca.id, "escalated_to": recipients}


@router.post("/{car_id}/reassign-auditee")
async def reassign_car_auditee(
    car_id: int,
    payload: ReassignAuditeeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_auditor(current_user)

    actor_name = " ".join(
        part for part in [current_user.first_name, current_user.last_name] if part
    ).strip()

    result = await reassign_car_by_auditor(
        car_id=car_id,
        new_email=payload.new_auditee_email,
        reason=payload.reason,
        db=db,
        actor_name=actor_name or current_user.email,
    )
    return {"ok": True, **result}


class ResendCarNotificationsRequest(BaseModel):
    only_pending: bool = True


@router.post("/{audit_id}/resend-car-notifications")
async def resend_car_notifications(
    audit_id: int,
    payload: ResendCarNotificationsRequest = ResendCarNotificationsRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Re-send the CAR notification email (same layout as report execution) to every
    auditee that has corrective actions on this audit. Useful when the original
    notification was never delivered or the auditee was assigned after the fact.
    """
    require_auditor(current_user)
    return await resend_car_notifications_for_audit(
        audit_id=audit_id,
        db=db,
        only_pending=payload.only_pending,
    )


class AuditCARsResponse(BaseModel):
    items: List[CorrectiveActionItem]
    total: int


@router.get("/{audit_id}/corrective-actions", response_model=AuditCARsResponse)
def get_audit_corrective_actions(
    audit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    user_is_auditor = _is_auditor(current_user)

    audit = db.query(Audit).filter(Audit.id == audit_id).first()
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    latest_history_subq = (
        db.query(
            CorrectiveActionHistory.corrective_action_id.label("car_id"),
            func.max(CorrectiveActionHistory.id).label("latest_history_id"),
        )
        .group_by(CorrectiveActionHistory.corrective_action_id)
        .subquery()
    )
    LatestHistory = aliased(CorrectiveActionHistory)

    rows = (
        db.query(
            CorrectiveAction.id.label("id"),
            CorrectiveAction.identifier.label("identifier"),
            CorrectiveAction.action_type.label("action_type"),
            CorrectiveAction.linked_action_id.label("linked_action_id"),
            CorrectiveAction.audit_answer_id.label("audit_answer_id"),
            CorrectiveAction.reason_why.label("reason_why"),
            CorrectiveAction.root_cause.label("root_cause"),
            CorrectiveAction.implemented_solution.label("implemented_solution"),
            CorrectiveAction.finding.label("migrated_finding"),
            CorrectiveAction.migrated_question_text.label("migrated_question_text"),
            CorrectiveAction.due_date.label("due_date"),
            CorrectiveAction.submission_due_at.label("submission_due_at"),
            CorrectiveAction.closure_due_at.label("closure_due_at"),
            CorrectiveAction.immediate_action_required.label("immediate_action_required"),
            CorrectiveAction.status.label("status"),
            CorrectiveAction.escalated.label("escalated"),
            CorrectiveAction.created_at.label("created_at"),
            CorrectiveAction.submitted_at.label("submitted_at"),
            CorrectiveAction.reassigned_from_email.label("reassigned_from_email"),
            CorrectiveAction.cc_emails.label("cc_emails_raw"),
            CorrectiveAction.submitted_by_email.label("submitted_by_email"),
            CorrectiveAction.submission_channel.label("submission_channel"),
            AuditAuditee.email.label("auditee_email"),
            User.email.label("auditor_email"),
            SecondAuditor.email.label("second_auditor_email"),
            Question.description.label("question_description"),
            Question.chapter.label("chapter"),
            AuditAnswer.fail.label("fail"),
            AuditAnswer.improve.label("improve"),
            AuditAnswer.pass_.label("pass_flag"),
            AuditAnswer.finding_text.label("finding_text"),
            AuditAnswer.process.label("process"),
            AuditAnswer.standard_paragraph.label("standard_paragraph"),
            AuditAnswer.classification.label("classification"),
            LatestHistory.comment.label("review_comment"),
        )
        .filter(CorrectiveAction.audit_id == audit_id)
        # ── this join was missing — needed for users.id = audits.auditor_id ──
        .join(Audit, Audit.id == CorrectiveAction.audit_id)
        .outerjoin(AuditAuditee, AuditAuditee.id == CorrectiveAction.auditee_id)
        .outerjoin(AuditAnswer, AuditAnswer.id == CorrectiveAction.audit_answer_id)
        .outerjoin(Question, Question.id == AuditAnswer.question_id)
        .outerjoin(User, User.id == Audit.auditor_id)
        .outerjoin(SecondAuditor, SecondAuditor.id == Audit.second_auditor_id)
        .outerjoin(
            latest_history_subq,
            latest_history_subq.c.car_id == CorrectiveAction.id,
        )
        .outerjoin(
            LatestHistory,
            LatestHistory.id == latest_history_subq.c.latest_history_id,
        )
        .order_by(CorrectiveAction.created_at.desc().nullslast())
        .all()
    )

    items: list[CorrectiveActionItem] = []
    for row in rows:
        finding_type = None
        if row.fail:
            finding_type = "FAIL"
        elif row.improve:
            finding_type = "IMPROVE"
        elif row.pass_flag:
            finding_type = "PASS"

        item = CorrectiveActionItem(
            id=row.id,
            auditId=audit_id,
            identifier=row.identifier,
            action_type=row.action_type,
            linked_action_id=row.linked_action_id,
            auditAnswerId=row.audit_answer_id,
            audit_reference=audit.audit_number,
            plant_name=audit.plant,
            finding_type=finding_type,
            corrective_action=row.question_description or row.migrated_question_text or row.migrated_finding,
            finding_text=row.migrated_finding or row.finding_text,
            process=row.process,
            standard_paragraph=row.standard_paragraph,
            classification=row.classification,
            chapter=row.chapter,
            auditee=row.auditee_email or "",
            pilotUser=_pilot_label(row),
            reason_why=row.reason_why,
            root_cause=row.root_cause,
            implemented_solution=row.implemented_solution,
            reassigned_from_email=row.reassigned_from_email,
            cc_emails=_parse_cc_list(row.cc_emails_raw),
            submitted_by_email=row.submitted_by_email,
            submission_channel=row.submission_channel,
            due_date=row.due_date.isoformat() if row.due_date else None,
            submission_due_at=row.submission_due_at.isoformat() if row.submission_due_at else None,
            closure_due_at=row.closure_due_at.isoformat() if row.closure_due_at else None,
            immediate_action_required=bool(row.immediate_action_required),
            submitted_at=(
                row.submitted_at.strftime("%d/%m/%Y %H:%M")
                if row.submitted_at
                else None
            ),
            created_at=(
                row.created_at.strftime("%d/%m/%Y %H:%M") if row.created_at else None
            ),
            status=db_status_to_ui(row.status),
            escalated=bool(row.escalated),
            review_comment=row.review_comment,
            documents_count=0,
        )

        item.documents = _load_related_documents(
            db,
            corrective_action_id=item.id,
            audit_answer_id=item.auditAnswerId,
            audit_id=item.auditId,
            reason_why=item.reason_why,
        )
        item.documents_count = len(item.documents)
        if not user_is_auditor:
            _apply_non_auditor_visibility(item)
        items.append(item)

    return AuditCARsResponse(items=items, total=len(items))
