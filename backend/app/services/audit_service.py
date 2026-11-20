import logging
import json
import hashlib
import os
from math import ceil
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from app.models.audit import Audit
from app.models.audit_answr import AuditAnswer
from app.models.audit_auditee import AuditAuditee
from app.models.audit_reschedule_history import AuditRescheduleHistory
from app.models.CarUnavailability import AuditUnavailability
from app.models.corrective_action import (
    CorrectiveAction,
    ACTION_TYPE_CORRECTIVE,
    ACTION_TYPE_IMMEDIATE,
)
from app.models.document import Document
from app.models.outlookSubscription import OutlookSubscription
from app.models.questionnaire import Questionnaire
from app.models.user import User
from app.routers.car_admin import DocumentItem
from app.schemas.QuestionAnswer import AuditAnswerOut, AuditAnswersResponse, QuestionOut
from app.schemas.auditSchema.auditSchema import (
    AuditCancelRequest,
    AuditDraftRequest,
    AuditeeOut,
    AuditPlanCreate,
    AuditPlanningDetailsResponse,
    AuditPlanningDetailsUpdate,
    AuditPlanningSyncResponse,
    AuditRescheduleRequest,
    AuditResponse,
    ExecuteAuditRequest,
    QuestionnaireMini,
    UserMini,
    auditeeAvailability,
)
from app.services.blob_storage_service import _extract_blob_name, delete_blob_sync
from app.services.event_calendar import (
    cancel_outlook_event,
    create_graph_subscription,
    get_access_token,
    get_graph_event,
    modify_outlook_event,
)
from app.services.questionnaire_service import get_questionnaire
from app.services.role_access_service import can_view_silent_box, has_auditor_role
from app.services.scoring_service import (
    IATF_PM,
    OPEN,
    calculate_audit_score,
    resolve_scoring_profile, VDA_P1_POTENTIAL,
)
from app.services.user_service import get_user_by_id
import httpx
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import and_, asc, desc, func, or_, text
import traceback
from app.utils.due_date import (
    PLANT_COUNTRY,
    build_holidays_for_plant,
    compute_due_date,
    get_holiday_details_for_plant,
    is_working_day,
)
from app.utils.retry_event_failure import safe_create_event, safe_is_user_available
from app.utils.send_car_email import build_car_form_url, generate_car_token, send_email
from app.utils.utility import generate_audit_number, parse_name_from_email
import uuid
from app.services.vda_scoring_service import compute_vda_results
from app.models.question import Question
from app.models.question_requirement import QuestionRequirement
from app.models.audit_answer_requirement import AuditAnswerRequirement

logging.basicConfig(level=logging.INFO)
OUTLOOK_LOCAL_TIMEZONE = os.environ.get("OUTLOOK_LOCAL_TIMEZONE", "Africa/Lagos")

DRAFT_ANSWER_PREFIX = "D"
MAX_DRAFT_IDENTIFIER_LEN = 20


CANCEL_REASON_LABELS: dict[int, str] = {
    1: "Auditee did not respond",
    2: "Auditee is on holiday",
    3: "Auditor is on leave",
    4: "Auditee is not available",
}
CANCEL_REASON_OTHER = 99


def _get_draft_answers(db: Session, audit_id: int) -> list[AuditAnswer]:
    return (
        db.query(AuditAnswer)
        .filter(
            AuditAnswer.audit_id == audit_id,
            AuditAnswer.identifier.like(f"{DRAFT_ANSWER_PREFIX}%"),
        )
        .order_by(AuditAnswer.id.asc())
        .all()
    )


def _delete_draft_answers(db: Session, audit_id: int) -> None:
    draft_answers = _get_draft_answers(db, audit_id)
    for answer in draft_answers:
        # Explicitly remove linked documents first (no DB cascade configured)
        docs = db.query(Document).filter(Document.audit_answer_id == answer.id).all()
        for d in docs:
            db.delete(d)
        db.delete(answer)


def _delete_audit_answers(db: Session, audit_id: int) -> None:
    answers = (
        db.query(AuditAnswer)
        .filter(AuditAnswer.audit_id == audit_id)
        .all()
    )
    for answer in answers:
        docs = db.query(Document).filter(Document.audit_answer_id == answer.id).all()
        for doc in docs:
            db.delete(doc)
        reqs = (
            db.query(AuditAnswerRequirement)
            .filter(AuditAnswerRequirement.audit_answer_id == answer.id)
            .all()
        )
        for req in reqs:
            db.delete(req)
        db.delete(answer)


def _normalize_email_list(emails: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for email in emails:
        value = str(email).strip().lower()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def resolve_auditee_inputs(data) -> list[tuple[str, Optional[int]]]:
    """(email, people_id) pairs for whichever auditee field the caller sent.

    `data.auditees` (list of {email, people_id}, from the Northwind directory
    picker) takes priority when present and non-empty. Falls back to the
    plain `data.auditee_emails` list (people_id=None for all) so existing
    callers that only send emails keep working unchanged - this is purely
    additive, `auditee_emails` is never required to also be consistent with
    `auditees`.
    """
    raw_auditees = getattr(data, "auditees", None)
    if raw_auditees:
        seen: set[str] = set()
        resolved: list[tuple[str, Optional[int]]] = []
        for item in raw_auditees:
            email = str(item.email).strip().lower()
            if not email or email in seen:
                continue
            seen.add(email)
            resolved.append((email, item.people_id))
        if resolved:
            return resolved

    return [
        (email, None)
        for email in _normalize_email_list([str(e) for e in data.auditee_emails])
    ]


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(OUTLOOK_LOCAL_TIMEZONE))
    return dt.astimezone(timezone.utc)


def _format_audit_planning_event(audit: Audit) -> tuple[str, str, list[str]]:
    auditee_emails = _normalize_email_list(
        [aa.email for aa in audit.auditees if aa.email]
    )
    hardware_email = (audit.hardware_email or "").strip().lower()
    auditee_names = [
        f"{first} {last}".strip()
        for first, last in (parse_name_from_email(email) for email in auditee_emails)
    ]
    auditees_text = ", ".join(auditee_names) or "N/A"
    questionnaire_type = getattr(
        getattr(audit.questionnaire, "audit_type", None), "value", None
    )
    formatted_date = audit.planned_start_date.strftime("%Y-%m-%d")
    second_auditor = getattr(audit, "second_auditor", None)
    second_auditor_row = (
        f"""
          <tr>
            <td style="padding:8px;"><b>Second Auditor:</b></td>
            <td style="padding:8px;">{second_auditor.first_name} {second_auditor.last_name}</td>
          </tr>"""
        if second_auditor
        else ""
    )
    subject = (
        f"[Northwind] Audit #{audit.audit_number} | Plant: {audit.plant} | "
        f"Sector: {audit.sector or 'N/A'} - {formatted_date}"
    )
    body = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial, sans-serif; color:#333; margin:0; padding:0;">
      <div style="background:#004b8d; padding:20px; color:white;">
        <h2 style="margin:0; font-size:22px;">Northwind - Audit Notification</h2>
        <p style="margin:5px 0 0 0; font-size:14px;">
          Audit #{audit.audit_number} | {audit.plant} | {audit.sector or "N/A"}
        </p>
      </div>
      <div style="padding:20px;">
        <h3 style="color:#004b8d; border-bottom:1px solid #ddd; padding-bottom:5px;">Audit Details</h3>
        <table style="border-collapse: collapse; width: 100%; max-width: 650px; font-size:14px;">
          <tr style="background:#f7f9fc;">
            <td style="padding:8px; width:150px;"><b>Auditor:</b></td>
            <td style="padding:8px;">{audit.auditor.first_name} {audit.auditor.last_name}</td>
          </tr>{second_auditor_row}
          <tr>
            <td style="padding:8px;"><b>Auditee(s)</b></td>
            <td style="padding:8px;">{auditees_text}</td>
          </tr>
          <tr style="background:#f7f9fc;">
            <td style="padding:8px;"><b>Plant:</b></td>
            <td style="padding:8px;">{audit.plant}</td>
          </tr>
          <tr>
            <td style="padding:8px;"><b>Sector:</b></td>
            <td style="padding:8px;">{audit.sector or "N/A"}</td>
          </tr>
          <tr style="background:#f7f9fc;">
            <td style="padding:8px;"><b>Date:</b></td>
            <td style="padding:8px;">{audit.planned_start_date.date().isoformat()}</td>
          </tr>
          <tr>
            <td style="padding:8px;"><b>Time:</b></td>
            <td style="padding:8px;">{audit.planned_start_date.strftime("%H:%M")} -> {audit.planned_end_date.strftime("%H:%M")}</td>
          </tr>
          <tr style="background:#f7f9fc;">
            <td style="padding:8px;"><b>Questionnaire:</b></td>
            <td style="padding:8px;">{audit.questionnaire.name if audit.questionnaire else "N/A"}</td>
          </tr>
          <tr>
            <td style="padding:8px;"><b>Audit Type:</b></td>
            <td style="padding:8px;">{questionnaire_type or "N/A"}</td>
          </tr>
          <tr style="background:#f7f9fc;">
            <td style="padding:8px;"><b>Supervisor:</b></td>
            <td style="padding:8px;">{audit.supervisor_email or "N/A"}</td>
          </tr>
          <tr>
            <td style="padding:8px;"><b>Hardware Email:</b></td>
            <td style="padding:8px;">{audit.hardware_email or "N/A"}</td>
          </tr>
        </table>
        <p style="margin-top:20px; font-size:14px; color:#555;">
          Please ensure all required documents and resources are available before the audit.
          For any updates or constraints, kindly inform the auditor in advance.
        </p>
        <div style="margin-top:30px; padding-top:10px; border-top:1px solid #ddd; font-size:12px; color:#777;">
          Northwind Group · Internal Quality Audit System<br/>
          This is an automated notification - please do not reply.
        </div>
      </div>
    </body>
    </html>
    """
    attendees = _normalize_email_list(
        [
            audit.auditor.email,
            *([second_auditor.email] if second_auditor and second_auditor.email else []),
            *auditee_emails,
            *([hardware_email] if hardware_email else []),
        ]
    )
    return subject, body, attendees


async def _ensure_outlook_subscription_for_auditor(
    db: Session, auditor_email: str
) -> None:
    existing_sub = (
        db.query(OutlookSubscription).filter_by(user_email=auditor_email).first()
    )
    if existing_sub and existing_sub.expires_at:
        current_utc = datetime.now(timezone.utc)
        expires_at = existing_sub.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at > current_utc:
            return

    sub = await create_graph_subscription(auditor_email)
    expires_at = datetime.fromisoformat(
        sub["expirationDateTime"].replace("Z", "+00:00")
    )
    if existing_sub:
        existing_sub.subscription_id = sub["id"]
        existing_sub.expires_at = expires_at
    else:
        db.add(
            OutlookSubscription(
                user_email=auditor_email,
                subscription_id=sub["id"],
                expires_at=expires_at,
            )
        )
    db.commit()


def _user_mini(user) -> Optional[UserMini]:
    if not user:
        return None
    return UserMini(
        id=user.id,
        first_name=user.first_name,
        last_name=user.last_name,
        email=user.email,
    )


def _audit_auditor_ids(audit: Audit) -> list[int]:
    """Lead auditor first, then the optional second auditor."""
    return [
        uid
        for uid in (audit.auditor_id, getattr(audit, "second_auditor_id", None))
        if uid
    ]


def _build_planning_details_response(
    audit: Audit,
    *,
    calendar_sync_needed: Optional[bool] = None,
) -> AuditPlanningDetailsResponse:
    auditor = audit.auditor
    questionnaire = audit.questionnaire
    return AuditPlanningDetailsResponse(
        audit_id=audit.id,
        audit_number=audit.audit_number,
        status=audit.status,
        event_created=bool(audit.event_created),
        event_id=audit.event_id,
        calendar_sync_needed=calendar_sync_needed,
        plant=audit.plant,
        sector=audit.sector,
        supervisor_email=audit.supervisor_email,
        hardware_email=audit.hardware_email,
        audit_date=audit.planned_start_date.date(),
        start_time=audit.planned_start_date.time(),
        end_time=audit.planned_end_date.time(),
        auditee_emails=[aa.email for aa in audit.auditees if aa.email],
        auditee_details=[
            AuditeeOut(email=aa.email, people_id=aa.people_id)
            for aa in audit.auditees
            if aa.email
        ],
        auditor=
        UserMini(
            id=auditor.id,
            first_name=auditor.first_name,
            last_name=auditor.last_name,
            email=auditor.email,
        )
        if auditor
        else None,
        second_auditor=_user_mini(getattr(audit, "second_auditor", None)),
        questionnaire_id=questionnaire.id if questionnaire else None,
        questionnaire=
        QuestionnaireMini(
            name=questionnaire.name,
            type=getattr(
                getattr(questionnaire, "audit_type", None), "value", None
            ),
        )
        if questionnaire
        else None,
    )


def resolve_history_display_action_type(
    action_type: Optional[str], reason: Optional[str]
) -> Optional[str]:
    """
    Normalize legacy rows for display: before migration e8f1c2d3b4a5 added a
    native 'cancelled' value to the audit_action enum, cancel_audit's backward
    -compat fallback recorded cancellations as action_type='postponed' with a
    '[cancelled]'-prefixed reason (that fallback has since been removed, but
    old rows written under it still exist). Treat those as cancellations.
    """
    if str(action_type or "").lower() == "cancelled":
        return "cancelled"
    if str(reason or "").lower().startswith("[cancelled]"):
        return "cancelled"
    return action_type


def _is_cancel_history_event(item) -> bool:
    return (
        resolve_history_display_action_type(
            getattr(item, "action_type", None), getattr(item, "reason", None)
        )
        == "cancelled"
    )


def _build_audit_response(audit: Audit) -> AuditResponse:
    auditor = audit.auditor
    questionnaire = audit.questionnaire
    cancel_reason = None
    if getattr(audit, "reschedules", None):
        cancel_events = [
            item for item in audit.reschedules if _is_cancel_history_event(item)
        ]
        if cancel_events:
            latest = max(
                cancel_events,
                key=lambda item: getattr(item, "created_at", None)
                or datetime.min.replace(tzinfo=timezone.utc),
            )
            cancel_reason = getattr(latest, "reason", None)
    return AuditResponse(
        id=audit.id,
        audit_number=audit.audit_number,
        status=audit.status,
        event_created=bool(audit.event_created),
        planned_start_date=audit.planned_start_date,
        planned_end_date=audit.planned_end_date,
        plant=audit.plant,
        sector=audit.sector,
        supervisor_email=audit.supervisor_email,
        auditor=
        UserMini(
            id=auditor.id,
            first_name=auditor.first_name,
            last_name=auditor.last_name,
            email=auditor.email,
        )
        if auditor
        else None,
        second_auditor=_user_mini(getattr(audit, "second_auditor", None)),
        auditees=[aa.email for aa in audit.auditees if aa.email],
        auditee_details=[
            AuditeeOut(email=aa.email, people_id=aa.people_id)
            for aa in audit.auditees
            if aa.email
        ],
        questionnaire=
        QuestionnaireMini(
            name=questionnaire.name,
            type=getattr(
                getattr(questionnaire, "audit_type", None), "value", None
            ),
        )
        if questionnaire
        else None,
        actual_start_date=audit.actual_start_date,
        actual_end_date=audit.actual_end_date,
        weak_points=audit.weak_points,
        strong_points=audit.strong_points,
        total_score=audit.total_score,
        report_exists=bool(audit.report_url),
        cancel_reason=cancel_reason,
    )


def _get_audit_for_planning(audit_id: int, db: Session) -> Audit:
    audit = (
        db.query(Audit)
        .options(
            joinedload(Audit.auditor),
            joinedload(Audit.questionnaire).joinedload(Questionnaire.audit_type),
            joinedload(Audit.auditees),
        )
        .filter(Audit.id == audit_id)
        .first()
    )
    if not audit:
        raise HTTPException(404, "Audit not found")
    if audit.status not in ("planned", "rescheduled"):
        raise HTTPException(
            status_code=400,
            detail="Planning details can only be edited for planned or rescheduled audits.",
        )
    return audit


# ─────────────────────────────────────────────────────────────────────────────
# FIX: get_vda_questions_by_audit
#   - Only returns PARENT questions  (e.g. P2.1, P4.3  — exactly 2 segments)
#   - Sub-questions (P2.1.1, P4.3.2 — 3 segments) are now stored in
#     question_requirements and returned nested inside each parent's
#     "requirements" list.
# ─────────────────────────────────────────────────────────────────────────────
def _fetch_vda_parent_questions(
    questionnaire_id: int, db: Session, *, is_potential_analysis: bool
) -> list[dict]:
    # ── Only fetch parent-level questions: pattern P<digits>.<digits>
    #    This excludes sub-questions like P2.1.1 (3 segments) which have
    #    already been migrated into question_requirements by the SQL script.
    questions = (
        db.query(Question)
        .filter(
            Question.questionnaire_id == questionnaire_id,
            Question.question_code.op("~")(r"^P[0-9]+\.[0-9]+$"),  # exactly 2 segments
        )
        .order_by(Question.question_code.asc())
        .all()
    )

    if not questions:
        return []

    # ── Batch-fetch all requirements for these parent questions
    qids = [q.id for q in questions]
    requirements = (
        db.query(QuestionRequirement)
        .filter(QuestionRequirement.question_id.in_(qids))
        .order_by(
            QuestionRequirement.question_id.asc(),
            QuestionRequirement.sort_order.asc(),
            QuestionRequirement.id.asc(),
        )
        .all()
    )

    requirements_by_question_id: dict[int, list[QuestionRequirement]] = {}
    for req in requirements:
        requirements_by_question_id.setdefault(req.question_id, []).append(req)

    return [
        {
            "id": q.id,
            "question_id": q.id,
            "question_text_en": getattr(q, "description", None)
            or getattr(q, "question_text_en", "")
            or "",
            "description": getattr(q, "description", None)
            or getattr(q, "question_text_en", "")
            or "",
            "question_code": getattr(q, "question_code", None)
            or getattr(q, "standard_paragraph", None)
            or "",
            "element": getattr(q, "element", None) or "",
            "critical_value": getattr(q, "critical_value", 0),
            "weight": getattr(q, "weight", 0),
            "subgroup": getattr(q, "subgroup", None),
            "is_asterisk": getattr(q, "is_asterisk", False),
            "source_questionnaire_id": questionnaire_id,
            "is_potential_analysis": is_potential_analysis,
            # ── Requirements nested here (was always [] before the fix) ──
            "requirements": [
                {
                    "id": req.id,
                    "question_id": req.question_id,
                    "requirement_code": req.requirement_code,
                    "description": req.description,
                    "sort_order": req.sort_order,
                }
                for req in requirements_by_question_id.get(q.id, [])
            ],
        }
        for q in questions
    ]


def get_vda_questions_by_audit(audit_id: int, db: Session):
    audit = (
        db.query(Audit)
        .filter(Audit.id == audit_id)
        .options(joinedload(Audit.questionnaire))
        .first()
    )

    if not audit or not audit.questionnaire:
        return []

    questions = _fetch_vda_parent_questions(
        audit.questionnaire.id, db, is_potential_analysis=False
    )

    if audit.include_potential_analysis and audit.questionnaire.potential_analysis_questionnaire_id:
        questions += _fetch_vda_parent_questions(
            audit.questionnaire.potential_analysis_questionnaire_id,
            db,
            is_potential_analysis=True,
        )

    return questions


def _maybe_delete_blob_if_unreferenced(
    db: Session, file_url: Optional[str], excluded_audit_answer_ids: set[int]
) -> None:
    """
    Delete blob only if no Document outside current draft answers references the same file_url.
    """
    if not file_url:
        return

    ref_exists = (
        db.query(Document.id)
        .filter(
            Document.file_url == file_url,
            ~Document.audit_answer_id.in_(excluded_audit_answer_ids),
        )
        .first()
    )
    if ref_exists:
        return

    blob_name = _extract_blob_name(file_url)
    if not blob_name:
        return
    try:
        delete_blob_sync(blob_name)
    except Exception as exc:
        logging.warning("Could not delete blob '%s': %s", blob_name, exc)


def _sanitize_draft_row_id(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    candidate = "".join(ch for ch in str(raw) if ch.isalnum() or ch in ("-", "_"))
    candidate = candidate.strip()
    return candidate[:12] if candidate else None


def _build_draft_answer_identifier(
    raw_question_id: Optional[int],
    draft_row_id: Optional[str] = None,
) -> str:
    # Keep identifier <= 20 chars (audit_answers.identifier is String(20))
    raw_qid = 0 if raw_question_id is None else raw_question_id
    sanitized_row_id = _sanitize_draft_row_id(draft_row_id) or uuid.uuid4().hex[:8]
    prefix = f"{DRAFT_ANSWER_PREFIX}{raw_qid}_"
    suffix_len = max(1, MAX_DRAFT_IDENTIFIER_LEN - len(prefix))
    return f"{prefix}{sanitized_row_id[:suffix_len]}"


def _extract_raw_question_id_from_draft_identifier(
    identifier: Optional[str],
) -> Optional[int]:
    if not identifier:
        return None
    if "_" not in identifier:
        return None
    left = identifier.split("_", 1)[0]
    if not left.startswith(DRAFT_ANSWER_PREFIX):
        return None
    qid_str = left[len(DRAFT_ANSWER_PREFIX) :]
    try:
        qid = int(qid_str)
    except ValueError:
        return None
    return None if qid == 0 else qid


def _extract_draft_row_id_from_identifier(identifier: Optional[str]) -> Optional[str]:
    if not identifier or "_" not in identifier:
        return None
    left, right = identifier.split("_", 1)
    if not left.startswith(DRAFT_ANSWER_PREFIX):
        return None
    row_id = _sanitize_draft_row_id(right)
    return row_id if row_id else None


def _encode_draft_finding_payload(
    finding_text: Optional[str],
    request_car: Optional[bool],
    car_reason: Optional[str],
) -> Optional[str]:
    payload = {
        "finding_text": finding_text or "",
        "request_car": bool(request_car),
        "car_reason": car_reason or "",
    }
    return json.dumps(payload, ensure_ascii=True)


def _decode_draft_finding_payload(raw: Optional[str]) -> dict[str, Any]:
    if not raw:
        return {"finding_text": "", "request_car": False, "car_reason": ""}
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return {
                "finding_text": parsed.get("finding_text") or "",
                "request_car": bool(parsed.get("request_car", False)),
                "car_reason": parsed.get("car_reason") or "",
            }
    except Exception:
        pass
    # Backward compatibility: old plain-text drafts
    return {"finding_text": raw, "request_car": False, "car_reason": ""}


def _raise_400(message: str) -> None:
    raise HTTPException(status_code=400, detail=message)


def _norm_text(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _resolve_cancel_reason_label(reason_code: int, reason_note: Optional[str]) -> str:
    if reason_code == CANCEL_REASON_OTHER:
        return "Other reason"
    return CANCEL_REASON_LABELS.get(reason_code, "Unspecified reason")


def _build_cancel_reason_text(reason_code: int, reason_note: Optional[str]) -> str:
    label = _resolve_cancel_reason_label(reason_code, reason_note)
    note = (reason_note or "").strip()
    return (
        f"[{reason_code}] {label}" if not note else f"[{reason_code}] {label} - {note}"
    )


def _collect_audit_participant_emails(audit: Audit) -> list[str]:
    recipients = {a.email.strip().lower() for a in (audit.auditees or []) if a.email}
    if getattr(audit, "auditor", None) and audit.auditor.email:
        recipients.add(audit.auditor.email.strip().lower())
    second_auditor = getattr(audit, "second_auditor", None)
    if second_auditor and second_auditor.email:
        recipients.add(second_auditor.email.strip().lower())
    # The supervisor (plant manager) is intentionally excluded from participant
    # notifications (reschedule, cancellation, auditee updates) per auditor request.
    return sorted(recipients)


def _audit_sender_kwargs(audit: Audit) -> dict[str, Optional[str]]:
    auditor = getattr(audit, "auditor", None)
    auditor_email = getattr(auditor, "email", None)
    sender_name = None
    if auditor and (auditor.first_name or auditor.last_name):
        sender_name = " ".join(
            part for part in [auditor.first_name, auditor.last_name] if part
        ).strip()
    return {
        "sender_email": auditor_email,
        "sender_name": sender_name or auditor_email,
        "reply_to": auditor_email,
    }


def _build_reschedule_notification_body(
    audit: Audit,
    old_start: datetime,
    old_end: datetime,
    new_start: datetime,
    new_end: datetime,
    reason: Optional[str],
) -> str:
    auditees = (
        ", ".join(sorted(a.email for a in (audit.auditees or []) if a.email)) or "N/A"
    )
    reason_text = (reason or "").strip() or "No reason provided."
    return (
        "<p>The following audit has been rescheduled.</p>"
        f"<p><strong>Audit:</strong> {audit.audit_number}</p>"
        f"<p><strong>Plant:</strong> {audit.plant}</p>"
        f"<p><strong>Sector:</strong> {audit.sector}</p>"
        f"<p><strong>Auditor:</strong> {getattr(getattr(audit, 'auditor', None), 'email', 'N/A')}</p>"
        + (
            f"<p><strong>Second Auditor:</strong> {audit.second_auditor.email}</p>"
            if getattr(audit, "second_auditor", None)
            else ""
        )
        +
        f"<p><strong>Auditee(s):</strong> {auditees}</p>"
        f"<p><strong>Previous schedule:</strong> {old_start.strftime('%Y-%m-%d %H:%M')} to {old_end.strftime('%Y-%m-%d %H:%M')}</p>"
        f"<p><strong>New schedule:</strong> {new_start.strftime('%Y-%m-%d %H:%M')} to {new_end.strftime('%Y-%m-%d %H:%M')}</p>"
        f"<p><strong>Reason:</strong> {reason_text}</p>"
    )


async def _notify_audit_reschedule(
    db: Session,
    audit: Audit,
    old_start: datetime,
    old_end: datetime,
    new_start: datetime,
    new_end: datetime,
    reason: Optional[str],
) -> None:
    participant_emails = _collect_audit_participant_emails(audit)
    if not participant_emails:
        return
    try:
        await send_email(
            subject=f"[Northwind] Audit {audit.audit_number} rescheduled",
            recipients=participant_emails,
            body_html=_build_reschedule_notification_body(
                audit=audit,
                old_start=old_start,
                old_end=old_end,
                new_start=new_start,
                new_end=new_end,
                reason=reason,
            ),
            db=db,
            context="audit_rescheduled",
            **_audit_sender_kwargs(audit),
        )
    except Exception as exc:
        logging.warning(
            "Failed to send audit reschedule email for audit_id=%s: %s",
            audit.id,
            exc,
        )


async def _notify_auditee_update(
    db: Session,
    audit: Audit,
    previous_auditee_emails: list[str],
    actor_email: str,
) -> None:
    current_auditee_emails = sorted(
        {a.email.strip().lower() for a in (audit.auditees or []) if a.email}
    )
    previous_set = {email.strip().lower() for email in previous_auditee_emails if email}
    current_set = set(current_auditee_emails)
    added = sorted(current_set - previous_set)
    removed = sorted(previous_set - current_set)

    recipients = sorted(
        set(previous_set) | current_set | set(_collect_audit_participant_emails(audit))
    )
    if not recipients:
        return

    added_html = ", ".join(added) if added else "None"
    removed_html = ", ".join(removed) if removed else "None"
    current_html = (
        ", ".join(current_auditee_emails) if current_auditee_emails else "None"
    )

    try:
        await send_email(
            subject=f"[Northwind] Audit {audit.audit_number} auditees updated",
            recipients=recipients,
            body_html=(
                f"<p>Audit <strong>{audit.audit_number}</strong> has updated auditee participants.</p>"
                f"<p><strong>Updated by:</strong> {actor_email}</p>"
                f"<p><strong>Current auditees:</strong> {current_html}</p>"
                f"<p><strong>Added:</strong> {added_html}</p>"
                f"<p><strong>Removed:</strong> {removed_html}</p>"
                f"<p><strong>Schedule:</strong> "
                f"{audit.planned_start_date.strftime('%Y-%m-%d %H:%M')} to "
                f"{audit.planned_end_date.strftime('%Y-%m-%d %H:%M')}</p>"
            ),
            db=db,
            context="audit_auditees_updated",
            **_audit_sender_kwargs(audit),
        )
    except Exception as exc:
        logging.warning(
            "Failed to send audit auditee update email for audit_id=%s: %s",
            audit.id,
            exc,
        )


async def _notify_audit_cancellation(
    db: Session,
    audit: Audit,
    reason_code: int,
    reason_note: Optional[str],
) -> None:
    label = _resolve_cancel_reason_label(reason_code, reason_note)
    note = (reason_note or "").strip()
    # timeline_hint = "You can reschedule this audit later while preserving traceability."
    # message = (
    #     f"Audit {audit.audit_number} was cancelled. Reason: {label}."
    #     + (f" Note: {note}." if note else "")
    #     + f" {timeline_hint}"
    # )
    participant_emails = _collect_audit_participant_emails(audit)
    if participant_emails:
        try:
            await send_email(
                subject=f"[Northwind] Audit {audit.audit_number} cancelled",
                recipients=participant_emails,
                body_html=(
                    f"<p>Audit <strong>{audit.audit_number}</strong> has been cancelled.</p>"
                    f"<p><strong>Reason:</strong> {label}</p>"
                    + (f"<p><strong>Note:</strong> {note}</p>" if note else "")
                    + "<p>You can still reschedule this audit later from the application.</p>"
                ),
                db=db,
                context="audit_cancelled",
                **_audit_sender_kwargs(audit),
            )
        except Exception as exc:
            logging.warning(
                "Failed to send audit cancellation email for audit_id=%s: %s",
                audit.id,
                exc,
            )


def _is_iso_classification_mode(questionnaire: Optional[Questionnaire]) -> bool:
    if not questionnaire:
        return False
    haystack = " ".join(
        [
            _norm_text(getattr(questionnaire, "name", None)),
            _norm_text(
                getattr(getattr(questionnaire, "audit_type", None), "value", None)
            ),
            _norm_text(
                getattr(getattr(questionnaire, "framework", None), "code", None)
            ),
            _norm_text(
                getattr(getattr(questionnaire, "framework", None), "label", None)
            ),
        ]
    )
    return (
        "iso14001" in haystack
        or "iso 14001" in haystack
        or "iso45001" in haystack
        or "iso 45001" in haystack
        or "iso50001" in haystack
        or "iso 50001" in haystack
        or "iso" in haystack
    )


# Open audits: result chosen per typed question -> (pass, improve, fail), and
# the stored value (<= 5 lets the auditor request a CAR, like other checklists).
OPEN_RESULT_TRIAGE = {
    "Conformity": (1, 0, 0),
    "Observation": (0, 1, 0),
    "Nonconformity": (0, 0, 1),
}
OPEN_RESULT_VALUE = {"Conformity": 10, "Observation": 5, "Nonconformity": 0}


def _classification_to_triage(
    classification: Optional[str],
) -> Optional[tuple[int, int, int]]:
    """
    Returns (pass_, improve, fail) from classification, or None if classification
    is not one of the supported ISO labels.
    """
    cls = _norm_text(classification)
    if cls in {"major nc", "major nonconformity", "major"}:
        return (0, 0, 1)
    if cls in {"minor nc", "minor nonconformity", "minor"}:
        return (0, 0, 1)
    if cls in {"ofi", "observation", "opportunity for improvement", "improvement"}:
        return (0, 1, 0)
    if cls in {"conformity", "conform", "compliant", "pass", "ok"}:
        return (1, 0, 0)
    return None


def _ensure_valid_plant_calendar(plant: str, years: set[int]) -> set[date]:
    plant_key = (plant or "").strip().lower()
    try:
        return build_holidays_for_plant(plant_key, years)
    except ValueError:
        known_plants = ", ".join(sorted(PLANT_COUNTRY.keys()))
        _raise_400(
            f"Unknown plant '{plant}'. Calendar validation failed. Valid plants: {known_plants}."
        )


def _validate_schedule_on_working_days(
    plant: str, start_dt: datetime, end_dt: datetime
) -> None:
    years = {start_dt.date().year, end_dt.date().year, start_dt.date().year + 1}
    holiday_set = _ensure_valid_plant_calendar(plant, years)
    holiday_details = get_holiday_details_for_plant(plant, years)

    day = start_dt.date()
    last_day = end_dt.date()
    while day <= last_day:
        if not is_working_day(day, holiday_set):
            if day.weekday() >= 5:
                _raise_400(
                    f"Selected schedule is on a weekend for plant '{plant}' ({day.isoformat()}). "
                    "Please choose a working day."
                )
            holiday_name = holiday_details.get(day, "Plant holiday")
            _raise_400(
                f"Selected schedule falls on '{holiday_name}' for plant '{plant}' ({day.isoformat()}). "
                "Please choose another date."
            )
        day += timedelta(days=1)


def _assert_no_approved_leave_overlap(
    db: Session,
    auditee_email: str,
    start_dt: datetime,
    end_dt: datetime,
) -> None:
    email = (auditee_email or "").strip().lower()
    if not email:
        return

    window_start = start_dt.date()
    window_end = end_dt.date()

    approved_overlaps = (
        db.query(AuditUnavailability)
        .filter(
            AuditUnavailability.status == "approved",
            func.lower(AuditUnavailability.requested_by_email) == email,
            AuditUnavailability.start_date <= window_end,
            AuditUnavailability.end_date >= window_start,
        )
        .order_by(AuditUnavailability.start_date.asc())
        .all()
    )

    if not approved_overlaps:
        return

    first = approved_overlaps[0]
    _raise_400(
        f"Auditee {auditee_email} already has an approved leave from "
        f"{first.start_date.isoformat()} to {first.end_date.isoformat()} "
        f"(request #{first.id}). Please choose another date/time window."
    )


# -------------------------
# Availability checkers
# -------------------------
def check_auditor_availability(
    db: Session,
    auditor_id: int,
    start_time: datetime,
    end_time: datetime,
    exclude_audit_id: int | None = None,
):
    query = db.query(Audit).filter(
        or_(Audit.auditor_id == auditor_id, Audit.second_auditor_id == auditor_id),
        Audit.planned_start_date < end_time,
        Audit.planned_end_date > start_time,
    )

    if exclude_audit_id:
        query = query.filter(Audit.id != exclude_audit_id)

    conflict = query.first()

    if conflict:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Auditor already has a conflicting audit ({conflict.audit_number}) "
                "in the selected time window."
            ),
        )


class _PlanningUpdateOutcome:
    """
    What actually changed as a result of a planning-details edit, so the
    caller can log/notify exactly like reschedule_audit and
    update_audit_auditees do for the same underlying changes — editing the
    date via this endpoint must not be a silent, untracked alternative to
    the dedicated /reschedule action.
    """

    def __init__(
        self,
        *,
        date_changed: bool,
        old_start: datetime,
        old_end: datetime,
        auditees_changed: bool,
        old_auditee_emails: list[str],
        new_auditee_emails: list[str],
    ) -> None:
        self.date_changed = date_changed
        self.old_start = old_start
        self.old_end = old_end
        self.auditees_changed = auditees_changed
        self.old_auditee_emails = old_auditee_emails
        self.new_auditee_emails = new_auditee_emails


async def _validate_and_apply_planning_update(
    audit: Audit,
    data: AuditPlanningDetailsUpdate,
    db: Session,
) -> _PlanningUpdateOutcome:
    planned_start = datetime.combine(data.audit_date, data.start_time)
    planned_end = datetime.combine(data.audit_date, data.end_time)
    if planned_start >= planned_end:
        _raise_400("End time must be after start time.")

    _validate_schedule_on_working_days(data.plant, planned_start, planned_end)

    resolved_auditees = resolve_auditee_inputs(data)
    normalized_auditees = [email for email, _ in resolved_auditees]
    if not normalized_auditees:
        _raise_400("At least one auditee email is required.")

    current_auditees = _normalize_email_list(
        [aa.email for aa in audit.auditees if aa.email]
    )
    old_start = audit.planned_start_date
    old_end = audit.planned_end_date
    schedule_unchanged = (
        old_start == planned_start
        and old_end == planned_end
        and current_auditees == normalized_auditees
    )

    if schedule_unchanged:
        audit.plant = data.plant
        audit.sector = data.sector
        audit.supervisor_email = data.supervisor_email
        audit.hardware_email = data.hardware_email
        return _PlanningUpdateOutcome(
            date_changed=False,
            old_start=old_start,
            old_end=old_end,
            auditees_changed=False,
            old_auditee_emails=current_auditees,
            new_auditee_emails=normalized_auditees,
        )

    for email in normalized_auditees:
        _assert_no_approved_leave_overlap(
            db=db,
            auditee_email=email,
            start_dt=planned_start,
            end_dt=planned_end,
        )
        try:
            available = await safe_is_user_available(email, planned_start, planned_end)
        except httpx.RequestError:
            raise HTTPException(
                status_code=503,
                detail=f"Availability service is temporarily unavailable for {email}. Please retry.",
            )
        if not available:
            _raise_400(
                f"Auditee {email} is not available in the selected date/time window."
            )

    for auditor_id in _audit_auditor_ids(audit):
        check_auditor_availability(
            db=db,
            auditor_id=auditor_id,
            start_time=planned_start,
            end_time=planned_end,
            exclude_audit_id=audit.id,
        )

    questionnaire = get_questionnaire(audit.questionnaire_id, db)
    if (questionnaire.get("status") or "").strip().lower() != "ready to use":
        raise HTTPException(
            status_code=400,
            detail="Only 'Ready to Use' questionnaires can remain planned for audits.",
        )

    audit.plant = data.plant
    audit.sector = data.sector
    audit.supervisor_email = data.supervisor_email
    audit.hardware_email = data.hardware_email
    audit.planned_start_date = planned_start
    audit.planned_end_date = planned_end

    db.query(AuditAuditee).filter(AuditAuditee.audit_id == audit.id).delete()
    for email, people_id in resolved_auditees:
        db.add(AuditAuditee(audit_id=audit.id, email=email, people_id=people_id))

    return _PlanningUpdateOutcome(
        date_changed=(old_start != planned_start or old_end != planned_end),
        old_start=old_start,
        old_end=old_end,
        auditees_changed=(current_auditees != normalized_auditees),
        old_auditee_emails=current_auditees,
        new_auditee_emails=normalized_auditees,
    )


def get_audit_planning_details(
    audit_id: int, db: Session
) -> AuditPlanningDetailsResponse:
    audit = _get_audit_for_planning(audit_id, db)
    return _build_planning_details_response(audit)


async def update_audit_planning_details(
    audit_id: int,
    data: AuditPlanningDetailsUpdate,
    db: Session,
    actor: User,
) -> AuditPlanningDetailsResponse:
    audit = _get_audit_for_planning(audit_id, db)
    outcome = await _validate_and_apply_planning_update(audit, data, db)

    # Editing the date/time here is another way of rescheduling the audit —
    # it must leave the same trail (history row, status flip, notification)
    # as the dedicated /reschedule endpoint, or this becomes a silent,
    # untracked way to move an audit's date.
    if outcome.date_changed:
        db.add(
            AuditRescheduleHistory(
                audit_id=audit.id,
                action_type="rescheduled",
                old_date=outcome.old_start,
                new_date=audit.planned_start_date,
                reason="Rescheduled via planning details edit.",
                changed_by=actor.id,
                created_at=datetime.now(timezone.utc),
            )
        )
        audit.status = "rescheduled"

    if outcome.auditees_changed:
        old_set = set(outcome.old_auditee_emails)
        new_set = set(outcome.new_auditee_emails)
        added = sorted(new_set - old_set)
        removed = sorted(old_set - new_set)
        db.add(
            AuditRescheduleHistory(
                audit_id=audit.id,
                action_type="auditees_updated",
                old_date=None,
                new_date=None,
                reason=(
                    f"Auditees updated by {actor.email} via planning details edit. "
                    f"Added: {', '.join(added) or 'None'}. "
                    f"Removed: {', '.join(removed) or 'None'}."
                ),
                changed_by=actor.id,
                created_at=datetime.now(timezone.utc),
            )
        )

    db.commit()
    db.refresh(audit)
    audit = _get_audit_for_planning(audit_id, db)

    if outcome.date_changed:
        await _notify_audit_reschedule(
            db=db,
            audit=audit,
            old_start=outcome.old_start,
            old_end=outcome.old_end,
            new_start=audit.planned_start_date,
            new_end=audit.planned_end_date,
            reason="Updated via planning details edit.",
        )
    if outcome.auditees_changed:
        await _notify_auditee_update(
            db=db,
            audit=audit,
            previous_auditee_emails=outcome.old_auditee_emails,
            actor_email=actor.email,
        )

    return _build_planning_details_response(audit, calendar_sync_needed=True)


async def sync_audit_planning_event(
    audit_id: int, db: Session
) -> AuditPlanningSyncResponse:
    audit = _get_audit_for_planning(audit_id, db)
    subject, body, attendees = _format_audit_planning_event(audit)

    event_action = "updated" if audit.event_id else "created"
    current_event = None
    if audit.event_id:
        access_token = await get_access_token()
        current_event = await get_graph_event(
            audit.event_id,
            access_token,
            audit.auditor.email,
        )
        if current_event.get("isCancelled"):
            # Stored event_id no longer exists in Outlook (deleted/cancelled
            # manually) — recreate a fresh event instead of trying to modify
            # an event that is gone.
            current_event = None
            event_action = "recreated"

    if current_event is not None:
        current_attendees = sorted(
            {
                (a.get("emailAddress", {}).get("address") or "").strip().lower()
                for a in current_event.get("attendees", [])
                if (a.get("emailAddress", {}).get("address") or "").strip()
            }
        )
        desired_attendees = sorted(
            {email.strip().lower() for email in attendees if email.strip()}
        )

        current_subject = current_event.get("subject")
        current_body = (current_event.get("body", {}) or {}).get("content")
        current_start_raw = (
            (current_event.get("start", {}) or {}).get("dateTime") or ""
        ).replace("Z", "+00:00")
        current_end_raw = (
            (current_event.get("end", {}) or {}).get("dateTime") or ""
        ).replace("Z", "+00:00")
        desired_start = _as_utc(audit.planned_start_date)
        desired_end = _as_utc(audit.planned_end_date)

        start_changed = True
        end_changed = True
        try:
            if current_start_raw:
                start_changed = (
                    datetime.fromisoformat(current_start_raw) != desired_start
                )
            if current_end_raw:
                end_changed = datetime.fromisoformat(current_end_raw) != desired_end
        except ValueError:
            start_changed = True
            end_changed = True

        await modify_outlook_event(
            audit.auditor.email,
            audit.event_id,
            new_start=audit.planned_start_date if start_changed else None,
            new_end=audit.planned_end_date if end_changed else None,
            attendees_emails=attendees
            if current_attendees != desired_attendees
            else None,
            subject=subject if current_subject != subject else None,
            body_text=body if current_body != body else None,
        )
    else:
        created_event = await safe_create_event(
            subject,
            audit.planned_start_date,
            audit.planned_end_date,
            attendees,
            body,
            audit.auditor.email,
        )
        audit.event_id = created_event.id

    audit.event_created = True
    db.commit()
    db.refresh(audit)

    try:
        await _ensure_outlook_subscription_for_auditor(db, audit.auditor.email)
    except Exception as exc:
        db.rollback()
        print("Subscription creation failed:", exc)
        traceback.print_exc()

    return AuditPlanningSyncResponse(
        ok=True,
        audit_id=audit.id,
        event_action=event_action,
        event_created=bool(audit.event_created),
        event_id=audit.event_id,
    )


async def check_auditee_availability(data: auditeeAvailability, db: Session):

    # Merge datetime
    planned_start = datetime.combine(data.audit_date, data.start_time)
    planned_end = datetime.combine(data.audit_date, data.end_time)
    if planned_start >= planned_end:
        _raise_400("End time must be after start time.")

    # -------------------------
    # Check auditee availability with retry
    # -------------------------
    for email in data.auditee_emails:
        if data.allow_unavailable_auditee:
            continue
        _assert_no_approved_leave_overlap(
            db=db,
            auditee_email=email,
            start_dt=planned_start,
            end_dt=planned_end,
        )
        try:
            available = await safe_is_user_available(email, planned_start, planned_end)
        except httpx.RequestError:
            raise HTTPException(
                status_code=503,
                detail=f"Availability service is temporarily unavailable for {email}. Please retry.",
            )
        if not available:
            _raise_400(
                f"Auditee {email} is not available in the selected date/time window."
            )
    return available


# -------------------------
# Document+ car creation
# -------------------------


def _create_documents_for_answer(
    db: Session,
    audit_answer_id: int,
    documents,
    corrective_action_id: Optional[int],
) -> None:
    now = datetime.now(timezone.utc)

    for doc in documents or []:
        db.add(
            Document(
                filename=doc.filename,
                mimetype=doc.mimetype,
                size=doc.size,
                file_url=doc.file_url,
                audit_answer_id=audit_answer_id,
                corrective_action_id=corrective_action_id,
                uploaded_at=now,
            )
        )


# -------------------------
# Main plan_audit function
# -------------------------
async def plan_audit(db: Session, data: AuditPlanCreate) -> AuditResponse:
    # -------------------------
    # Validate auditor and questionnaire
    # -------------------------
    auditor = get_user_by_id(data.auditor_id, db)
    if not auditor:
        raise HTTPException(404, "Auditor not found")
    second_auditor = None
    if data.second_auditor_id:
        if data.second_auditor_id == auditor.id:
            _raise_400("The second auditor must be different from the lead auditor.")
        second_auditor = get_user_by_id(data.second_auditor_id, db)
        if not has_auditor_role(second_auditor):
            _raise_400("The selected second auditor does not have the auditor role.")
    questionnaire = get_questionnaire(data.questionnaire_id, db)
    if (questionnaire.get("status") or "").strip().lower() != "ready to use":
        raise HTTPException(
            status_code=400,
            detail="Only 'Ready to Use' questionnaires can be planned for audits.",
        )

    # Potential Analysis (P1) is automatically included whenever the selected
    # questionnaire has a linked Potential Analysis questionnaire — it's not an
    # opt-in choice made at planning time.
    questionnaire_row = (
        db.query(Questionnaire.potential_analysis_questionnaire_id)
        .filter(Questionnaire.id == data.questionnaire_id)
        .first()
    )
    include_potential_analysis = bool(questionnaire_row and questionnaire_row[0])

    # Merge datetime
    planned_start = datetime.combine(data.audit_date, data.start_time)
    planned_end = datetime.combine(data.audit_date, data.end_time)
    if planned_start >= planned_end:
        _raise_400("End time must be after start time.")

    _validate_schedule_on_working_days(data.plant, planned_start, planned_end)

    resolved_auditees = resolve_auditee_inputs(data)

    conflicts: list[str] = []
    # -------------------------
    # Check auditee availability
    # -------------------------
    for email, _ in resolved_auditees:
        if data.allow_unavailable_auditee:
            continue
        try:
            _assert_no_approved_leave_overlap(
                db=db,
                auditee_email=email,
                start_dt=planned_start,
                end_dt=planned_end,
            )
        except HTTPException as exc:
            if exc.status_code == 400 and exc.detail:
                conflicts.append(str(exc.detail))
            else:
                raise
        try:
            available = await safe_is_user_available(email, planned_start, planned_end)
        except httpx.RequestError:
            raise HTTPException(
                status_code=503,
                detail=f"Availability service is temporarily unavailable for {email}. Please retry.",
            )
        if not available:
            conflicts.append(
                f"Auditee {email} is not available in the selected date/time window."
            )

    # Check auditor availability in DB (unless override requested)
    if not data.allow_unavailable_auditee:
        for planned_auditor in filter(None, (auditor, second_auditor)):
            try:
                check_auditor_availability(
                    db, planned_auditor.id, planned_start, planned_end
                )
            except HTTPException as exc:
                if exc.status_code == 400 and exc.detail:
                    conflicts.append(
                        f"{planned_auditor.email}: {exc.detail}"
                        if second_auditor
                        else str(exc.detail)
                    )
                else:
                    raise

    if conflicts and not data.allow_unavailable_auditee:
        _raise_400(" | ".join(conflicts))

    # -------------------------
    # Reject duplicates (double-click / double submit)
    # -------------------------
    # The availability checks above don't stop two identical requests that
    # arrive together (and "Plan Anyway" skips the auditor check entirely),
    # so serialize on the audit's identity and refuse an identical one. The
    # advisory lock is released when the insert below commits.
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"plan_audit:{auditor.id}:{data.questionnaire_id}:{data.plant}:{planned_start.isoformat()}"},
    )
    duplicate = (
        db.query(Audit.audit_number)
        .filter(
            Audit.auditor_id == auditor.id,
            Audit.questionnaire_id == data.questionnaire_id,
            Audit.plant == data.plant,
            Audit.sector == data.sector,
            Audit.planned_start_date == planned_start,
            Audit.planned_end_date == planned_end,
            Audit.status.in_(["planned", "rescheduled"]),
        )
        .first()
    )
    if duplicate:
        db.rollback()
        _raise_400(
            f"This audit is already planned ({duplicate.audit_number}) for the same "
            "auditor, questionnaire, plant, sector and time."
        )

    # -------------------------
    # Create audit and auditees in DB
    # -------------------------
    try:
        audit_number = generate_audit_number()
        new_audit = Audit(
            status="planned",
            audit_number=audit_number,
            auditor_id=auditor.id,
            second_auditor_id=second_auditor.id if second_auditor else None,
            plant=data.plant,
            hardware_email=data.hardware_email,
            sector=data.sector,
            questionnaire_id=data.questionnaire_id,
            supervisor_email=data.supervisor_email,  # ✅ ADD THIS
            planned_start_date=planned_start,
            planned_end_date=planned_end,
            event_created=False,
            include_potential_analysis=include_potential_analysis,
        )

        db.add(new_audit)
        db.flush()  # get new_audit.id
        print("Flush successful, new_audit.id =", new_audit.id)

        for email, people_id in resolved_auditees:
            db.add(
                AuditAuditee(
                    audit_id=new_audit.id, email=email, people_id=people_id
                )
            )

        db.commit()
        db.refresh(new_audit)
        print("Audit and auditees committed successfully.")

    except SQLAlchemyError as e:
        db.rollback()
        print("TRACEBACK:")
        traceback.print_exc()
        print("Failed Audit Data:", new_audit.__dict__)
        raise HTTPException(500, f"Database error while planning audit: {e}")

    # -------------------------
    # Create Outlook Event
    # -------------------------
    # Reuse the same subject/body/attendees builder that every later sync
    # (reschedule, auditee update, explicit "sync" endpoint) uses, so the
    # very first invite already matches what subsequent syncs would send —
    # notably including hardware_email as an attendee from the start instead
    # of only picking it up on the next sync.
    try:
        subject, body, attendees = _format_audit_planning_event(new_audit)

        created_event = await safe_create_event(
            subject, planned_start, planned_end, attendees, body, auditor.email
        )

        new_audit.event_id = created_event.id
        new_audit.event_created = True
        db.commit()
        print("Event created in Outlook:", created_event.id)

    except Exception as e:
        print("⚠ Microsoft Calendar event creation failed:", e)

    # -------------------------
    # Check or create subscription for this auditor
    # -------------------------
    try:
        existing_sub = (
            db.query(OutlookSubscription).filter_by(user_email=auditor.email).first()
        )
        current_utc = datetime.now(timezone.utc)
        expires_at = existing_sub.expires_at if existing_sub else None
        if expires_at and expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if (
            not existing_sub
            or not expires_at
            or expires_at <= current_utc
        ):
            sub = await create_graph_subscription(auditor.email)
            print("subscription is", sub)
            expires_at = datetime.fromisoformat(
                sub["expirationDateTime"].replace("Z", "+00:00")
            )
            if existing_sub:
                existing_sub.subscription_id = sub["id"]
                existing_sub.expires_at = expires_at
            else:
                outlook_sub = OutlookSubscription(
                    user_email=auditor.email,
                    subscription_id=sub["id"],
                    expires_at=expires_at,
                )
                db.add(outlook_sub)
            db.commit()
            print("Subscription created for auditor:", auditor.email)
        else:
            print("Subscription already exists for auditor:", auditor.email)

    except Exception as e:
        db.rollback()
        print("⚠ Subscription creation failed:", e)
        traceback.print_exc()

    # -------------------------
    # Return AuditResponse
    # -------------------------
    return _build_audit_response(new_audit)


async def reschedule_audit(audit_id: int, data: AuditRescheduleRequest, db: Session):
    # Get audit
    audit = (
        db.query(Audit)
        .options(
            joinedload(Audit.auditor),
            joinedload(Audit.questionnaire),
            joinedload(Audit.auditees),
        )
        .filter(Audit.id == audit_id)
        .first()
    )
    if not audit:
        raise HTTPException(404, "Audit not found")

    new_start = data.new_start_date
    new_end = data.new_end_date

    if new_start >= new_end:
        _raise_400("Start time must be before end time.")

    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(404, f"User :{data.email} not found")

    _validate_schedule_on_working_days(audit.plant, new_start, new_end)

    # ------------------------------------------------------------
    # CHECK AUDITOR AVAILABILITY (DB)
    # ------------------------------------------------------------
    conflicts: list[str] = []
    if not data.allow_unavailable_auditee:
        for auditor_id in _audit_auditor_ids(audit):
            try:
                check_auditor_availability(
                    db=db,
                    auditor_id=auditor_id,
                    start_time=new_start,
                    end_time=new_end,
                    exclude_audit_id=audit_id,
                )
            except HTTPException as exc:
                if exc.status_code == 400 and exc.detail:
                    conflicts.append(str(exc.detail))
                else:
                    raise

    # ------------------------------------------------------------
    # CHECK AUDITEES AVAILABILITY (Outlook)
    # ------------------------------------------------------------
    for auditee in audit.auditees:
        if data.allow_unavailable_auditee:
            continue
        try:
            _assert_no_approved_leave_overlap(
                db=db,
                auditee_email=auditee.email,
                start_dt=new_start,
                end_dt=new_end,
            )
        except HTTPException as exc:
            if exc.status_code == 400 and exc.detail:
                conflicts.append(str(exc.detail))
            else:
                raise
        try:
            available = await safe_is_user_available(auditee.email, new_start, new_end)
        except httpx.RequestError:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Availability service is temporarily unavailable for {auditee.email}. "
                    "Please retry."
                ),
            )

        if not available:
            conflicts.append(
                f"Auditee {auditee.email} is not available in the selected date/time window."
            )

    if conflicts and not data.allow_unavailable_auditee:
        _raise_400(" | ".join(conflicts))

    # Save old values
    old_start = audit.planned_start_date
    old_end = audit.planned_end_date

    try:
        # History
        history = AuditRescheduleHistory(
            audit_id=audit_id,
            action_type="rescheduled",
            old_date=old_start,
            new_date=new_start,
            reason=data.reason,
            changed_by=user.id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(history)

        # Update audit
        audit.planned_start_date = new_start
        audit.planned_end_date = new_end
        audit.status = "rescheduled"

        db.commit()
        db.refresh(audit)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(500, "Database error while rescheduling")

    # ------------------------------------------------------------
    # SYNC OUTLOOK EVENT — creates one if this audit never got one in the
    # first place (e.g. the original planning sync failed silently), or
    # updates the existing event otherwise. Using the same create-or-update
    # logic as the "Retry Sync" button avoids silently no-op'ing when
    # event_id is still null at reschedule time.
    # ------------------------------------------------------------
    try:
        await sync_audit_planning_event(audit_id, db)
    except Exception as exc:
        print(f"sync_audit_planning_event failed during reschedule: {exc}")
        audit.event_created = False
        db.commit()

    await _notify_audit_reschedule(
        db=db,
        audit=audit,
        old_start=old_start,
        old_end=old_end,
        new_start=new_start,
        new_end=new_end,
        reason=data.reason,
    )

    # ------------------------------------------------------------
    # RETURN RESPONSE
    # ------------------------------------------------------------
    return _build_audit_response(audit)


def delete_audit(audit_id: int, db: Session) -> dict:
    audit = (
        db.query(Audit)
        .options(
            joinedload(Audit.answers),
            joinedload(Audit.auditees),
            joinedload(Audit.corrective_actions),
            joinedload(Audit.reschedules),
        )
        .filter(Audit.id == audit_id)
        .first()
    )
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    if audit.status not in ("planned", "rescheduled"):
        raise HTTPException(
            status_code=400,
            detail="Only planned or rescheduled audits can be deleted.",
        )

    if audit.corrective_actions:
        raise HTTPException(
            status_code=400,
            detail="Delete is not allowed when corrective actions already exist. Cancel the audit instead.",
        )

    _delete_draft_answers(db, audit_id)
    _delete_audit_answers(db, audit_id)

    for auditee in list(audit.auditees or []):
        db.delete(auditee)
    for reschedule in list(audit.reschedules or []):
        db.delete(reschedule)

    db.delete(audit)
    db.commit()
    return {"message": "Audit deleted successfully", "audit_id": audit_id}


async def cancel_audit(
    audit_id: int, data: AuditCancelRequest, db: Session
) -> AuditResponse:
    audit = (
        db.query(Audit)
        .options(
            joinedload(Audit.auditor),
            joinedload(Audit.questionnaire),
            joinedload(Audit.auditees),
        )
        .filter(Audit.id == audit_id)
        .first()
    )
    if not audit:
        raise HTTPException(404, "Audit not found")

    if audit.status in ("completed", "waiting_for_corrective_actions"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel audit in status '{audit.status}'.",
        )
    if audit.status == "cancelled":
        raise HTTPException(status_code=400, detail="Audit is already cancelled.")

    actor = db.query(User).filter(func.lower(User.email) == data.email.lower()).first()
    if not actor:
        raise HTTPException(404, f"User '{data.email}' not found")

    reason_code = int(data.reason_code)
    if reason_code not in CANCEL_REASON_LABELS and reason_code != CANCEL_REASON_OTHER:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported reason_code '{reason_code}'. Allowed values: 1,2,3,4,99.",
        )

    reason_text = _build_cancel_reason_text(reason_code, data.reason)
    old_start = audit.planned_start_date

    # NOTE: audit_action enum natively supports 'cancelled' as of migration
    # e8f1c2d3b4a5 — no backward-compat fallback is needed anymore.
    try:
        db.add(
            AuditRescheduleHistory(
                audit_id=audit.id,
                action_type="cancelled",
                old_date=old_start,
                new_date=None,
                reason=reason_text,
                changed_by=actor.id,
                created_at=datetime.now(timezone.utc),
            )
        )
        audit.status = "cancelled"
        audit.event_created = False
        db.commit()
        db.refresh(audit)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(500, "Database error while cancelling audit")

    await _notify_audit_cancellation(
        db=db,
        audit=audit,
        reason_code=reason_code,
        reason_note=data.reason,
    )

    if audit.event_id:
        try:
            await cancel_outlook_event(
                audit.auditor.email,
                audit.event_id,
                comment=f"Audit {audit.audit_number} cancelled. {reason_text}",
            )
        except httpx.HTTPStatusError as exc:
            print(f"cancel_outlook_event failed: {exc}")
        except httpx.RequestError as exc:
            print(f"cancel_outlook_event network failure: {exc}")

    return _build_audit_response(audit)


async def update_audit_auditees(audit_id: int, data, db: Session) -> AuditResponse:
    audit = (
        db.query(Audit)
        .options(
            joinedload(Audit.auditor),
            joinedload(Audit.questionnaire),
            joinedload(Audit.auditees),
        )
        .filter(Audit.id == audit_id)
        .first()
    )
    if not audit:
        raise HTTPException(404, "Audit not found")

    if audit.status not in ("planned", "rescheduled"):
        raise HTTPException(
            status_code=400,
            detail="Auditees can only be updated for planned or rescheduled audits.",
        )

    actor = db.query(User).filter(func.lower(User.email) == data.email.lower()).first()
    if not actor:
        raise HTTPException(404, f"User '{data.email}' not found")

    resolved_auditees = resolve_auditee_inputs(data)
    normalized_auditee_emails = [email for email, _ in resolved_auditees]
    people_id_by_email = {email: people_id for email, people_id in resolved_auditees}

    if not normalized_auditee_emails:
        raise HTTPException(status_code=400, detail="At least one auditee is required.")

    existing_auditee_emails = [
        a.email.strip().lower() for a in (audit.auditees or []) if a.email
    ]
    existing_set = set(existing_auditee_emails)
    added_emails = [
        email for email in normalized_auditee_emails if email not in existing_set
    ]

    conflicts: list[str] = []
    for auditee_email in added_emails:
        if data.allow_unavailable_auditee:
            continue
        try:
            _assert_no_approved_leave_overlap(
                db=db,
                auditee_email=auditee_email,
                start_dt=audit.planned_start_date,
                end_dt=audit.planned_end_date,
            )
        except HTTPException as exc:
            if exc.status_code == 400 and exc.detail:
                conflicts.append(str(exc.detail))
            else:
                raise
        try:
            available = await safe_is_user_available(
                auditee_email,
                audit.planned_start_date,
                audit.planned_end_date,
            )
        except httpx.RequestError:
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Availability service is temporarily unavailable for {auditee_email}. "
                    "Please retry."
                ),
            )
        if not available:
            conflicts.append(
                f"Auditee {auditee_email} is not available in the selected date/time window."
            )

    if conflicts:
        raise HTTPException(status_code=400, detail=" | ".join(conflicts))

    removed_emails = [
        email for email in existing_auditee_emails if email not in set(normalized_auditee_emails)
    ]
    auditees_changed = existing_set != set(normalized_auditee_emails)

    try:
        audit.auditees.clear()
        for auditee_email in normalized_auditee_emails:
            audit.auditees.append(
                AuditAuditee(
                    email=auditee_email,
                    people_id=people_id_by_email.get(auditee_email),
                )
            )
        if auditees_changed:
            # Auditee-list changes are a planning action too — log them the
            # same way reschedule/cancel do, so they show up in the audit's
            # history instead of being visible only through email.
            db.add(
                AuditRescheduleHistory(
                    audit_id=audit.id,
                    action_type="auditees_updated",
                    old_date=None,
                    new_date=None,
                    reason=(
                        f"Auditees updated by {actor.email}. "
                        f"Added: {', '.join(added_emails) or 'None'}. "
                        f"Removed: {', '.join(removed_emails) or 'None'}."
                    ),
                    changed_by=actor.id,
                    created_at=datetime.now(timezone.utc),
                )
            )
        db.commit()
        db.refresh(audit)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(500, "Database error while updating audit auditees")

    try:
        # Reuse the same create-or-modify logic as the planning sync endpoint so
        # newly added auditees always receive a real calendar invite, even if the
        # audit's original Outlook event creation had silently failed at plan time.
        await sync_audit_planning_event(audit.id, db)
    except Exception as exc:
        print(f"Calendar sync failed while updating auditees: {exc}")
        audit.event_created = False
        db.commit()

    await _notify_auditee_update(
        db=db,
        audit=audit,
        previous_auditee_emails=existing_auditee_emails,
        actor_email=actor.email,
    )

    return _build_audit_response(audit)


def execute_audit_service(
    db: Session,
    audit_id: int,
    payload: ExecuteAuditRequest,
) -> Dict[str, Any]:

    audit = (
        db.query(Audit)
        .options(
            joinedload(Audit.auditees),
            joinedload(Audit.questionnaire).joinedload(Questionnaire.audit_type),
            joinedload(Audit.questionnaire).joinedload(Questionnaire.framework),
            joinedload(Audit.questionnaire).joinedload(Questionnaire.questions),
        )
        .filter(Audit.id == audit_id)
        .first()
    )

    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    # Parse and set actual dates
    try:
        audit_date_str = payload.audit_date
        start_time_str = payload.start_time
        end_time_str = payload.end_time

        actual_start = datetime.strptime(
            f"{audit_date_str} {start_time_str}", "%Y-%m-%d %H:%M"
        )
        actual_end = datetime.strptime(
            f"{audit_date_str} {end_time_str}", "%Y-%m-%d %H:%M"
        )

        audit.actual_start_date = actual_start
        audit.actual_end_date = actual_end
        # consider created_at as audit completion time for now, since we don't have a separate "complete audit" action
        audit.created_at = datetime.now(timezone.utc)
    except ValueError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid date/time format: {str(e)}"
        )

    # Update audit summary (now optional for IATF NC)
    audit.strong_points = payload.strong_points or ""
    audit.weak_points = payload.weak_points or ""
    created_answers_count = 0
    cars_created = 0
    cars_for_email: list[dict] = []
    cars_by_auditee: dict[str, list[dict]] = {}
    total_pass = 0
    total_improve = 0
    total_fail = 0
    major_nc_count = 0
    minor_nc_count = 0
    ofi_count = 0

    # Fallback auditee: when the auditor doesn't pick one per finding, default to the
    # first auditee on the audit so a CAR is never created without an owner (even when
    # the audit has several auditees). An explicit per-finding selection still wins.
    audit_auditee_ids = {auditee.id for auditee in (audit.auditees or [])}
    audit_auditee_email_by_id = {
        auditee.id: (auditee.email or "").strip().lower()
        for auditee in (audit.auditees or [])
    }
    default_audit_auditee_id: Optional[int] = (
        audit.auditees[0].id if (audit.auditees or []) else None
    )

    # ✅ Detect IATF NC mode (negative question_id indicates IATF NC)
    is_iatf_nc_mode = any(answer.question_id < 0 for answer in payload.answers)

    # Remove any previously saved draft answers before final submission
    _delete_draft_answers(db, audit_id)

    is_iso_classification_mode = _is_iso_classification_mode(audit.questionnaire)
    questionnaire_questions = list(
        getattr(audit.questionnaire, "questions", None) or []
    )

    # Potential Analysis (P1) questions come from a linked questionnaire, not
    # audit.questionnaire.questions, so they're kept in a separate set/list
    # rather than merged into questionnaire_questions: the VDA process scoring
    # below (compute_vda_results) is scoped to questionnaire_questions only,
    # and must not see these answers.
    pa_question_ids: set[int] = set()
    potential_analysis_questions: list[Question] = []
    if audit.include_potential_analysis and getattr(
        audit.questionnaire, "potential_analysis_questionnaire_id", None
    ):
        potential_analysis_questions = list(
            db.query(Question)
            .filter(
                Question.questionnaire_id
                == audit.questionnaire.potential_analysis_questionnaire_id
            )
            .all()
        )
        pa_question_ids = {q.id for q in potential_analysis_questions}

    all_known_questions = questionnaire_questions + potential_analysis_questions
    server_critical_by_qid = {q.id: q.critical_value for q in all_known_questions}
    mandatory_by_qid = {
        q.id: 1 if (q.weight == 1) else 0 for q in all_known_questions
    }

    profile_key = resolve_scoring_profile(
        questionnaire_name=getattr(audit.questionnaire, "name", None),
        audit_type_value=getattr(
            getattr(audit.questionnaire, "audit_type", None), "value", None
        ),
        framework_code=getattr(
            getattr(audit.questionnaire, "framework", None), "code", None
        ),
        framework_label=getattr(
            getattr(audit.questionnaire, "framework", None), "label", None
        ),
        score_calculation=getattr(audit.questionnaire, "score_calculation", None),
        is_iatf_nc_mode=is_iatf_nc_mode,
    )
    is_iatf_pm_profile = profile_key == IATF_PM
    is_open_profile = profile_key == OPEN

    questionnaire_name = _norm_text(getattr(audit.questionnaire, "name", None))
    framework_code = _norm_text(
        getattr(getattr(audit.questionnaire, "framework", None), "code", None)
    )
    framework_label = _norm_text(
        getattr(getattr(audit.questionnaire, "framework", None), "label", None)
    )
    is_vda_audit = (
        "vda" in questionnaire_name
        or "vda" in framework_code
        or "vda" in framework_label
        or profile_key == "VDA_PROCESS"
    )
    is_vda_p1_audit = profile_key == VDA_P1_POTENTIAL

    # Process each answer
    for answer_data in payload.answers:
        if is_iatf_pm_profile and answer_data.question_id > 0:
            if answer_data.question_id not in mandatory_by_qid:
                raise HTTPException(
                    status_code=400,
                    detail=f"Question {answer_data.question_id} does not belong to this audit questionnaire.",
                )
            if (
                mandatory_by_qid[answer_data.question_id] == 1
                and answer_data.value == -1
            ):
                raise HTTPException(
                    status_code=400,
                    detail=f"Question {answer_data.question_id} is mandatory and cannot be optional.",
                )

        if answer_data.value == -1:
            continue

        is_pa_answer = answer_data.question_id in pa_question_ids

        if (
            is_vda_audit
            and not is_vda_p1_audit
            and not is_pa_answer
            and answer_data.value in {0, 4, 6, 8}
        ):
            resolved_car_reason = (
                (answer_data.car_reason or "").strip()
                or (answer_data.finding_text or "").strip()
            )
            if (
                not answer_data.request_car
                or not resolved_car_reason
            ):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"VDA question {answer_data.question_id} scored {answer_data.value}. "
                        "A CAR request and supporting findings are required for values 0, 4, 6, or 8."
                    ),
            )
            answer_data.car_reason = resolved_car_reason
        if (is_vda_p1_audit or is_pa_answer) and answer_data.value in {0, 4}:
            if not (answer_data.finding_text or "").strip():
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"P1 question {answer_data.question_id} scored {answer_data.value}. "
                        "Findings are required for Red/Yellow."
                    ),
                )
            if not (answer_data.documents and len(answer_data.documents) > 0):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"P1 question {answer_data.question_id} scored {answer_data.value}. "
                        "Evidence is required for Red/Yellow."
                    ),
                )

        # Open audit: the auditor typed both the question and the answer.
        if is_open_profile:
            triage = OPEN_RESULT_TRIAGE.get(answer_data.classification or "")
            if triage is None:
                raise HTTPException(
                    status_code=400,
                    detail="Open audit entries need a result: Conformity, Observation or Nonconformity.",
                )
            if not (answer_data.question_text or "").strip() or not (
                answer_data.finding_text or ""
            ).strip():
                raise HTTPException(
                    status_code=400,
                    detail="Open audit entries need both a question and an answer.",
                )
            pass_, improve, fail = triage
            answer_data.value = OPEN_RESULT_VALUE[answer_data.classification]
        # Handle IATF NC mode differently
        elif is_iatf_nc_mode:
            # For IATF NC: classification determines pass/fail/improve
            # Minor=1, Major=2, Improvement=3, Strong Point=4
            classification = answer_data.classification
            if classification not in {"Minor", "Major", "Improvement", "Strong Point"}:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid IATF classification. Allowed: Minor, Major, Improvement, Strong Point.",
                )
            fail = 1 if classification in ["Minor", "Major"] else 0
            improve = 1 if classification == "Improvement" else 0
            pass_ = 1 if classification == "Strong Point" else 0
            cls_norm = _norm_text(classification)
            if cls_norm == "major":
                major_nc_count += 1
            elif cls_norm == "minor":
                minor_nc_count += 1
            elif cls_norm == "improvement":
                ofi_count += 1
        else:
            classification_triage = (
                _classification_to_triage(answer_data.classification)
                if is_iso_classification_mode
                else None
            )
            if classification_triage is not None:
                pass_, improve, fail = classification_triage
                cls_norm = _norm_text(answer_data.classification)
                if cls_norm in {"major nc", "major nonconformity", "major"}:
                    major_nc_count += 1
                elif cls_norm in {"minor nc", "minor nonconformity", "minor"}:
                    minor_nc_count += 1
                elif cls_norm in {
                    "ofi",
                    "observation",
                    "opportunity for improvement",
                    "improvement",
                }:
                    ofi_count += 1
            else:
                if is_iatf_pm_profile:
                    # Plant Manager IATF value mode:
                    # 1-2 => fail, 3 => improve, 4-5 => pass
                    pass_ = 1 if answer_data.value >= 4 else 0
                    improve = 1 if answer_data.value == 3 else 0
                    fail = 1 if answer_data.value <= 2 else 0
                    # Continue to answer creation using this triage.
                elif is_iso_classification_mode:
                    raise HTTPException(
                        status_code=400,
                        detail="ISO audits require valid classification (Major NC, Minor NC, OFI, Conformity).",
                    )
                else:
                    if answer_data.question_id <= 0:
                        raise HTTPException(
                            status_code=400,
                            detail="Invalid question_id for value-based audit answer.",
                        )
                    if answer_data.question_id not in server_critical_by_qid:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Question {answer_data.question_id} does not belong to this audit questionnaire.",
                        )
                    server_critical_value = server_critical_by_qid[
                        answer_data.question_id
                    ]
                    # Standard audit logic (trust server-side critical value, not client payload)
                    pass_ = 1 if answer_data.value > server_critical_value else 0
                    fail = 1 if answer_data.value < server_critical_value else 0
                    improve = 1 if answer_data.value == server_critical_value else 0

        audit_answer = AuditAnswer(
            audit_id=audit_id,
            question_id=answer_data.question_id
            if answer_data.question_id > 0
            else None,
            value=answer_data.value,
            finding_text=answer_data.finding_text,
            question_text=answer_data.question_text,
            fail=fail,
            improve=improve,
            pass_=pass_,
            identifier=f"A-{uuid.uuid4().hex[:17]}",
            process=answer_data.process,
            standard_paragraph=answer_data.standard_paragraph,
            classification=answer_data.classification,
            silent_box=bool(answer_data.silent_box),
            created_at=datetime.now(timezone.utc),
        )
        db.add(audit_answer)
        db.flush()

        saved_requirements: list[AuditAnswerRequirement] = []
        for req_answer in answer_data.requirements:
            saved_req = AuditAnswerRequirement(
                audit_answer_id=audit_answer.id,
                question_requirement_id=req_answer.question_requirement_id,
                value=req_answer.value,
                fulfilled=req_answer.fulfilled,
                finding_text=req_answer.finding_text,
                evidence_json=json.dumps([d.model_dump() for d in req_answer.evidence]) if getattr(req_answer, "evidence", None) else None,
            )
            db.add(saved_req)
            saved_requirements.append(saved_req)
        if saved_requirements:
            db.flush()

        total_pass += pass_
        total_improve += improve
        total_fail += fail

        selected_auditee_id = answer_data.auditee_id
        if (
            selected_auditee_id is not None
            and selected_auditee_id not in audit_auditee_ids
        ):
            raise HTTPException(
                status_code=400,
                detail=f"Auditee {selected_auditee_id} is not assigned to this audit.",
            )

        cars = [] if (is_vda_p1_audit or is_pa_answer) else _maybe_create_car_iatf(
            db=db,
            identifier=answer_data.identifier or f"CA-{uuid.uuid4().hex[:17]}",
            audit_id=audit_id,
            audit_answer_id=audit_answer.id,
            value=answer_data.value,
            request_car=answer_data.request_car,
            car_reason=answer_data.car_reason,
            auditee_id=selected_auditee_id,
            default_auditee_id=default_audit_auditee_id,
            plant=audit.plant,
            is_iatf_nc_mode=is_iatf_nc_mode,
            is_iso_classification_mode=is_iso_classification_mode,
            is_vda_audit=is_vda_audit,
            classification=answer_data.classification,
            finding_text=answer_data.finding_text,
            immediate_action_required=bool(
                is_vda_audit and answer_data.immediate_action_required
            ),
        )

        if cars:
            cars_created += 1
            primary_car = cars[0]
            immediate_row = cars[1] if len(cars) > 1 else None

            if is_iatf_nc_mode or (
                is_iso_classification_mode and answer_data.classification
            ):
                car_type = answer_data.classification
                process = answer_data.process or "N/A"
                paragraph = answer_data.standard_paragraph or "N/A"
                question_text = f"NC {process} - {paragraph}"
            else:
                car_type = "Critical" if fail == 1 else "Improvement"
                question_text = (
                    audit_answer.question_text or f"Question {answer_data.question_id}"
                )

            # Exactly one token/email per finding, even when a linked immediate
            # row was also created -- it has no token of its own and is reached
            # through the same link via get_car_form_data's linked_action.
            token = generate_car_token(db, primary_car)
            form_url = build_car_form_url(token)

            car_email_payload = {
                "car_id": primary_car.id,
                "type": car_type,
                "question": question_text,
                "finding": audit_answer.finding_text or "",
                "reason": primary_car.reason_why or "",
                "due_date": primary_car.due_date,
                "form_url": form_url,
                "auditee_id": primary_car.auditee_id,
                "immediate_action_required": bool(immediate_row is not None),
                "submission_due_at": immediate_row.submission_due_at if immediate_row else None,
                "closure_due_at": immediate_row.closure_due_at if immediate_row else None,
            }
            cars_for_email.append(car_email_payload)

            auditee_email = audit_auditee_email_by_id.get(primary_car.auditee_id)
            if auditee_email:
                cars_by_auditee.setdefault(auditee_email, []).append(car_email_payload)

        # VDA sub-requirements are scored independently of their parent
        # question, so a requirement scored 0/4/6/8 is a finding of its own
        # and must raise its own CAR -- even when the parent scored 10.
        if is_vda_audit and not is_vda_p1_audit and not is_pa_answer:
            for saved_req in saved_requirements:
                req_value = int(saved_req.value) if saved_req.value is not None else None
                if req_value not in VDA_REQUIREMENT_CAR_VALUES:
                    continue
                req_finding = (saved_req.finding_text or "").strip()
                if not req_finding:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"VDA question {answer_data.question_id}: a requirement scored "
                            f"{req_value} needs findings, which are used for its CAR."
                        ),
                    )
                req_cars = _maybe_create_car_iatf(
                    db=db,
                    identifier=f"CA-{uuid.uuid4().hex[:17]}",
                    audit_id=audit_id,
                    audit_answer_id=audit_answer.id,
                    audit_answer_requirement_id=saved_req.id,
                    value=req_value,
                    request_car=True,
                    car_reason=req_finding,
                    auditee_id=selected_auditee_id,
                    default_auditee_id=default_audit_auditee_id,
                    plant=audit.plant,
                    is_vda_audit=True,
                    finding_text=req_finding,
                )
                if not req_cars:
                    continue
                req_car = req_cars[0]
                cars_created += 1
                question_requirement = db.get(
                    QuestionRequirement, saved_req.question_requirement_id
                )
                token = generate_car_token(db, req_car)
                req_critical = server_critical_by_qid.get(answer_data.question_id)
                req_payload = {
                    "car_id": req_car.id,
                    "type": (
                        "Critical"
                        if req_critical is None or req_value < req_critical
                        else "Improvement"
                    ),
                    "question": _requirement_car_question_text(
                        db.get(Question, answer_data.question_id), question_requirement
                    ),
                    "finding": req_finding,
                    "reason": req_car.reason_why or "",
                    "due_date": req_car.due_date,
                    "form_url": build_car_form_url(token),
                    "auditee_id": req_car.auditee_id,
                    "immediate_action_required": False,
                    "submission_due_at": None,
                    "closure_due_at": None,
                }
                cars_for_email.append(req_payload)
                auditee_email = audit_auditee_email_by_id.get(req_car.auditee_id)
                if auditee_email:
                    cars_by_auditee.setdefault(auditee_email, []).append(req_payload)

        _create_documents_for_answer(
            db=db,
            audit_answer_id=audit_answer.id,
            documents=answer_data.documents,
            corrective_action_id=cars[0].id if cars else None,
        )

        created_answers_count += 1

    # Update audit status
    audit.status = "waiting_for_corrective_actions" if cars_created > 0 else "completed"

    scoring = calculate_audit_score(
        total_pass=total_pass,
        total_improve=total_improve,
        total_fail=total_fail,
        profile_key=profile_key,
        major_nc_count=major_nc_count,
        minor_nc_count=minor_nc_count,
        ofi_count=ofi_count,
    )
    audit.total_score = scoring["score"]

    # ✅ VDA score calculation: keep everything else as-is
    vda_result = None

    if is_vda_audit and not is_vda_p1_audit:
        questions_by_id = {q.id: q for q in questionnaire_questions}
        vda_result = compute_vda_results(
            answers=payload.answers,
            questions_by_id=questions_by_id,
        )
        # Persist the displayed VDA score as the inferior/integer floor.
        vda_total = (vda_result or {}).get("total", {})
        audit.total_score = float(vda_total.get("display_score") or 0.0)
        audit.result_class = vda_total.get("final_rating")

        # Additive Potential Analysis (P1) result, when this VDA 6.3 audit
        # opted in and the auditor actually answered PA questions.
        pa_answers = [a for a in payload.answers if a.question_id in pa_question_ids]
        if pa_answers:
            pa_red = sum(1 for a in pa_answers if a.value == 0)
            pa_yellow = sum(1 for a in pa_answers if a.value == 4)
            pa_green = sum(1 for a in pa_answers if a.value == 10)
            pa_ne = sum(1 for a in pa_answers if a.value == -1)
            if pa_ne > 3:
                raise HTTPException(
                    status_code=400,
                    detail="Potential Analysis allows at most 3 n.e. answers.",
                )
            if pa_red >= 1 or pa_yellow > 12:
                pa_class = "R"
                pa_label = "Barred supplier"
            elif pa_yellow <= 6:
                pa_class = "G"
                pa_label = "Approved supplier"
            else:
                pa_class = "Y"
                pa_label = "Conditionally approved supplier"
            audit.potential_analysis_result_class = pa_class
            vda_result["p1_result"] = {
                "red": pa_red,
                "yellow": pa_yellow,
                "green": pa_green,
                "ne": pa_ne,
                "classification": pa_class,
                "label": pa_label,
            }
    elif is_vda_p1_audit:
        red = sum(1 for a in payload.answers if a.value == 0)
        yellow = sum(1 for a in payload.answers if a.value == 4)
        green = sum(1 for a in payload.answers if a.value == 10)
        ne = sum(1 for a in payload.answers if a.value == -1)
        if ne > 3:
            raise HTTPException(status_code=400, detail="P1 allows at most 3 n.e. answers.")
        if red >= 1 or yellow > 12:
            p1_class = "R"
            label = "Barred supplier"
        elif yellow <= 6:
            p1_class = "G"
            label = "Approved supplier"
        else:
            p1_class = "Y"
            label = "Conditionally approved supplier"
        audit.result_class = p1_class
        audit.total_score = float(max(0, 100 - red * 100 - yellow * 5))
        vda_result = {
            "p1_result": {
                "red": red,
                "yellow": yellow,
                "green": green,
                "ne": ne,
                "classification": p1_class,
                "label": label,
            }
        }
    db.commit()

    # Return execution response
    return {
        "message": "Audit executed successfully",
        "audit_id": audit_id,
        "status": audit.status,
        "answers_created": created_answers_count,
        "cars_created": cars_created,
        "auditees": [
            {"id": a.id, "email": a.email, "name": a.email.split("@")[0]}
            for a in audit.auditees
        ],
        "cars": cars_for_email,
        "cars_by_auditee": cars_by_auditee,
        "audit_reference": audit.audit_number,
        "vda_result": vda_result,
    }


# VDA requirement scores that raise a CAR (10 = fully met, n.e. = not scored).
VDA_REQUIREMENT_CAR_VALUES = {0, 4, 6, 8}


def _requirement_car_question_text(
    question: Optional[Question],
    question_requirement: Optional[QuestionRequirement],
) -> str:
    """Label for a requirement CAR: parent question code + requirement."""
    parts = []
    if question is not None:
        parts.append(question.question_code or f"Question {question.id}")
    if question_requirement is not None:
        req_label = question_requirement.description or ""
        if question_requirement.requirement_code:
            req_label = f"{question_requirement.requirement_code}: {req_label}"
        parts.append(req_label)
    return " - ".join(p for p in parts if p) or "VDA requirement"


def _maybe_create_car_iatf(
    db: Session,
    audit_id: int,
    audit_answer_id: int,
    value: int,
    request_car: bool,
    car_reason: Optional[str],
    auditee_id: Optional[int],
    default_auditee_id: Optional[int],
    plant: str,
    is_iatf_nc_mode: bool = False,
    is_iso_classification_mode: bool = False,
    is_vda_audit: bool = False,
    identifier: Optional[str] = None,
    classification: Optional[str] = None,
    finding_text: Optional[str] = None,
    immediate_action_required: bool = False,
    audit_answer_requirement_id: Optional[int] = None,
) -> list[CorrectiveAction]:
    """
    Create CAR(s) with logic that handles both standard audits and IATF NC mode.

    Standard mode: CAR created if request_car=True AND value <= 5 AND has reason
    IATF NC mode: CAR created if request_car=True AND classification in ["Minor", "Major"]

    When immediate_action_required is set, two linked rows are created instead of
    one: a "corrective" row (normal due_date, 11-workday cadence) and an
    "immediate" row (due_date left NULL, 24h submission / 48h closure cadence).
    Splitting them keeps the two obligations from fighting over one row's
    deadlines. Returns [] when no CAR should be created, [corrective] when the
    checkbox is off, or [corrective, immediate] when it's on.
    """

    cls = _norm_text(classification)

    if is_iatf_nc_mode:
        # In IATF NC mode, CAR can only be created for Minor or Major
        if cls not in {"minor", "major"}:
            return []
        if not request_car:
            return []
    elif is_vda_audit:
        # VDA: value 0/4 CAR is enforced before this function. For values 6/8/10,
        # the auditor may still request a CAR when useful.
        if not request_car:
            return []
        if not car_reason:
            return []
    elif is_iso_classification_mode:
        # ISO mode is classification-driven:
        # - Major/Minor NC => CAR mandatory (even if request_car was false)
        # - OFI/Conformity => CAR optional only when explicitly requested
        mandatory_nc = cls in {
            "major nc",
            "major nonconformity",
            "major",
            "minor nc",
            "minor nonconformity",
            "minor",
        }
        if mandatory_nc:
            request_car = True
            if not car_reason:
                car_reason = (
                    finding_text
                    or f"{classification or 'Nonconformity'} raised during audit"
                )
        else:
            if not request_car:
                return []
            if not car_reason:
                return []
    else:
        if not request_car:
            return []
        if value > 5 or not car_reason:
            return []

    # Calculate due date
    now = datetime.now(timezone.utc)
    try:
        due_base = compute_due_date(created_at=now, plant=plant, workdays=11)
    except ValueError:
        known_plants = ", ".join(sorted(PLANT_COUNTRY.keys()))
        _raise_400(
            f"Unknown plant '{plant}'. Calendar validation failed. Valid plants: {known_plants}."
        )
    submission_due_at = None
    closure_due_at = None
    if immediate_action_required:
        submission_due_at = now + timedelta(hours=24)
        closure_due_at = now + timedelta(hours=48)

    # Resolve the auditee: explicit per-finding selection, else the audit's default
    # (first) auditee. This is None only when the audit has no auditees at all.
    resolved_auditee_id = auditee_id if auditee_id is not None else default_auditee_id

    # A CAR with no auditee cannot be notified or accessed (its link would 403 for
    # everyone). This can only happen when the audit has no auditee assigned, so block
    # the submission instead of silently creating an orphaned CAR.
    if resolved_auditee_id is None:
        _raise_400(
            "A corrective action must be assigned to an auditee, but this audit has no "
            "auditee assigned. Please add at least one auditee to the audit before "
            "submitting corrective actions."
        )

    # Corrective row: the permanent, root-cause fix. Keeps the caller-supplied
    # identifier and stays the "primary" record (the one the emailed token
    # points at).
    corrective_car = CorrectiveAction(
        audit_id=audit_id,
        audit_answer_id=audit_answer_id,
        audit_answer_requirement_id=audit_answer_requirement_id,
        # A requirement CAR shares its parent's audit_answer, whose
        # finding_text is the parent's -- keep the requirement's own finding.
        finding=finding_text if audit_answer_requirement_id else None,
        reason_why=car_reason or "",
        status="pending",
        auditee_id=resolved_auditee_id,
        created_at=now,
        due_date_base=due_base,
        due_date=due_base,
        identifier=identifier,
        action_type=ACTION_TYPE_CORRECTIVE,
        immediate_action_required=False,
        submission_due_at=None,
        closure_due_at=None,
    )
    db.add(corrective_car)

    if not immediate_action_required:
        db.flush()
        return [corrective_car]

    # Immediate row: containment action, 24h/48h cadence. due_date/due_date_base
    # are left NULL on purpose -- process_car_followups and get_cars_due_in_days
    # both filter on "due_date != None", so this alone keeps the immediate row
    # out of the normal 15-day escalation/reminder cadence with no changes
    # needed there; it's only ever picked up by process_immediate_action_followups.
    immediate_car = CorrectiveAction(
        audit_id=audit_id,
        audit_answer_id=audit_answer_id,
        reason_why=car_reason or "",
        status="pending",
        auditee_id=resolved_auditee_id,
        created_at=now,
        due_date_base=None,
        due_date=None,
        identifier=f"CA-{uuid.uuid4().hex[:14]}-I",
        action_type=ACTION_TYPE_IMMEDIATE,
        immediate_action_required=True,
        submission_due_at=submission_due_at,
        closure_due_at=closure_due_at,
    )
    db.add(immediate_car)
    db.flush()

    corrective_car.linked_action_id = immediate_car.id
    immediate_car.linked_action_id = corrective_car.id
    db.flush()

    return [corrective_car, immediate_car]


def get_all_audits(db: Session):
    audits = (
        db.query(Audit)
        .options(
            joinedload(Audit.auditor),
            joinedload(Audit.second_auditor),
            joinedload(Audit.questionnaire).joinedload(Questionnaire.audit_type),
            joinedload(Audit.auditees),
            joinedload(Audit.reschedules),
        )
        .order_by(desc(Audit.planned_start_date))
        .all()
    )

    return [_build_audit_response(audit) for audit in audits]


def getAuditsByAuditor(
    db: Session,
    auditor_id: int,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
    from_date: Optional[date] = None,
):
    """
    Parameters
    ----------
    from_date
        When set, only audits with planned_start_date >= from_date are
        returned. The frontend now handles "from today" filtering client-
        side, so pass ``None`` (default) to get all dates.
    """
    try:
        query = (
            db.query(Audit)
            .options(
                joinedload(Audit.auditor),
                joinedload(Audit.second_auditor),
                joinedload(Audit.questionnaire).joinedload(Questionnaire.audit_type),
                joinedload(Audit.questionnaire).joinedload(Questionnaire.framework),
            )
            .filter(
                or_(
                    Audit.status.in_(["planned", "rescheduled", "cancelled"]),
                    # Done audits run in this app only; Monday-imported
                    # history has no questionnaire and stays off the calendar.
                    and_(
                        Audit.status.in_(
                            ["completed", "waiting_for_corrective_actions"]
                        ),
                        Audit.questionnaire_id.isnot(None),
                    ),
                )
            )
            .order_by(asc(Audit.planned_start_date))
        )

        # auditor_id=0 means "all auditors" (used by calendar-wide filter)
        if auditor_id > 0:
            query = query.filter(
                or_(
                    Audit.auditor_id == auditor_id,
                    Audit.second_auditor_id == auditor_id,
                )
            )

        if from_date is not None:
            query = query.filter(Audit.planned_start_date >= from_date)

        # No pagination (calendar mode - needs every event)
        if page is None or per_page is None:
            items = query.all()
            return {
                "items": [_serialize(a) for a in items],
                "page": 1,
                "per_page": len(items),
                "total": len(items),
                "total_pages": 1,
            }

        if per_page <= 0:
            raise HTTPException(
                status_code=400, detail="per_page must be greater than 0."
            )

        # Paginated (cards list)
        page = max(page, 1)
        total = query.count()
        offset = (page - 1) * per_page
        audits = query.offset(offset).limit(per_page).all()

        return {
            "items": [_serialize(a) for a in audits],
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": ceil(total / per_page),
        }
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        logging.exception(
            "Database error in getAuditsByAuditor(auditor_id=%s, page=%s, per_page=%s): %s",
            auditor_id,
            page,
            per_page,
            exc,
        )
        raise HTTPException(
            status_code=500, detail="Failed to fetch audits for auditor."
        )


def _serialize(audit: Audit) -> dict:
    """
    Flatten the ORM object into a plain dict that is safe to JSON-encode.
    Add audit_type_value and framework_label at the top level so the
    frontend doesn't have to traverse nested objects.
    """
    q = audit.questionnaire
    at = q.audit_type if q else None  # AuditType  (id, value)
    fw = q.framework if q else None  # Framework  (id, code, label)

    return {
        # ── core fields ────────────────────────────────────────────────────
        "id": audit.id,
        "audit_number": audit.audit_number,
        "status": audit.status,
        "plant": audit.plant,
        "sector": audit.sector,
        "event_created": audit.event_created,
        "auditor_id": audit.auditor_id,
        "second_auditor_id": audit.second_auditor_id,
        "planned_start_date": str(audit.planned_start_date),
        "planned_end_date": str(audit.planned_end_date),
        "actual_start_date": str(audit.actual_start_date)
        if audit.actual_start_date
        else None,
        "actual_end_date": str(audit.actual_end_date)
        if audit.actual_end_date
        else None,
        "total_score": float(audit.total_score) if audit.total_score is not None else None,
        "report_url": audit.report_url,
        # ── auditor ────────────────────────────────────────────────────────
        "auditor": {
            "id": audit.auditor.id,
            "first_name": audit.auditor.first_name,
            "last_name": audit.auditor.last_name,
            "email": getattr(audit.auditor, "email", None),
        }
        if audit.auditor
        else None,
        "second_auditor": {
            "id": audit.second_auditor.id,
            "first_name": audit.second_auditor.first_name,
            "last_name": audit.second_auditor.last_name,
            "email": getattr(audit.second_auditor, "email", None),
        }
        if audit.second_auditor
        else None,
        # ── auditees (list of email strings or objects, keep as-is) ───────
        "auditees": [
            getattr(ae, "email", None) or getattr(ae, "auditee_email", None) or str(ae)
            for ae in (audit.auditees or [])
        ],
        # Richer, additive alongside "auditees" above - carries people_id so
        # a picker re-opened from this list knows which auditees already
        # came from the Northwind directory instead of showing them all as manual.
        "auditee_details": [
            {"email": ae.email, "people_id": getattr(ae, "people_id", None)}
            for ae in (audit.auditees or [])
            if getattr(ae, "email", None)
        ],
        # ── questionnaire meta ─────────────────────────────────────────────
        "questionnaire_id": audit.questionnaire_id,
        "audit_type_id": at.id if at else None,
        "audit_type": at.value if at else None,  # e.g. "IATF", "ISO", "VDA"
        "framework_id": fw.id if fw else None,
        "framework_code": fw.code if fw else None,  # e.g. "IATF16949"
        "framework_label": fw.label if fw else None,  # e.g. "IATF 16949:2016"
    }


def _build_draft_answers_payload(db: Session, audit_id: int) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for a in _get_draft_answers(db, audit_id):
        restored_qid = (
            a.question_id
            if a.question_id is not None
            else _extract_raw_question_id_from_draft_identifier(a.identifier)
        )
        parsed_finding = _decode_draft_finding_payload(a.finding_text)
        docs = db.query(Document).filter(Document.audit_answer_id == a.id).all()
        payload.append(
            {
                "question_id": restored_qid,
                "draft_row_id": _extract_draft_row_id_from_identifier(a.identifier),
                "value": a.value,
                "finding_text": parsed_finding["finding_text"],
                "request_car": parsed_finding["request_car"],
                "car_reason": parsed_finding["car_reason"],
                "silent_box": bool(a.silent_box),
                "documents": [
                    {
                        "filename": d.filename,
                        "mimetype": d.mimetype,
                        "size": d.size,
                        "file_url": d.file_url,
                    }
                    for d in docs
                ],
                "process": a.process,
                "standard_paragraph": a.standard_paragraph,
                "classification": a.classification,
                "question_text": a.question_text,
            }
        )
    return payload


def _compute_draft_etag(
    audit: Audit, draft_answers_payload: list[dict[str, Any]]
) -> str:
    canonical = {
        "audit_id": audit.id,
        "audit_date": audit.actual_start_date.strftime("%Y-%m-%d")
        if audit.actual_start_date
        else None,
        "start_time": audit.actual_start_date.strftime("%H:%M")
        if audit.actual_start_date
        else None,
        "end_time": audit.actual_end_date.strftime("%H:%M")
        if audit.actual_end_date
        else None,
        "strong_points": audit.strong_points or "",
        "weak_points": audit.weak_points or "",
        "answers": draft_answers_payload,
    }
    serialized = json.dumps(
        canonical,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def save_audit_draft(audit_id: int, data: AuditDraftRequest, db: Session) -> dict:
    """
    Persist partial audit execution data as a draft.
    Does NOT change status or create answers/CARs.
    """
    audit = db.query(Audit).filter(Audit.id == audit_id).first()
    if not audit:
        raise HTTPException(404, "Audit not found")

    if audit.status not in ("planned", "rescheduled"):
        raise HTTPException(
            400, f"Cannot save draft: audit is already '{audit.status}'"
        )

    if data.expected_draft_etag is not None:
        current_payload = _build_draft_answers_payload(db, audit_id)
        current_etag = _compute_draft_etag(audit, current_payload)
        if data.expected_draft_etag != current_etag:
            raise HTTPException(
                status_code=409,
                detail="Draft was modified by another session. Please refresh and retry.",
            )

    now = datetime.now(timezone.utc)

    def _normalize_draft_date(raw_date: Optional[str]) -> Optional[str]:
        if raw_date is None:
            return None
        s = str(raw_date).strip()
        if not s:
            return None

        # Accept ISO datetime/date strings and keep only date part
        if "T" in s:
            s = s.split("T", 1)[0]
        elif " " in s and "-" in s:
            s = s.split(" ", 1)[0]

        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
            try:
                return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue

        raise HTTPException(
            status_code=400,
            detail="Invalid draft date/time format. Expected audit_date='YYYY-MM-DD' and time='HH:MM'",
        )

    def _normalize_draft_time(raw_time: Optional[str]) -> Optional[str]:
        if raw_time is None:
            return None
        s = str(raw_time).strip()
        if not s:
            return None

        # Full ISO datetime support
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return dt.strftime("%H:%M")
        except ValueError:
            pass

        # If coming as datetime text, keep only time component
        if "T" in s:
            s = s.split("T", 1)[1]
        if " " in s and "-" in s:
            try:
                dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
                return dt.strftime("%H:%M")
            except ValueError:
                pass

        # Remove timezone/milliseconds suffixes from time-only values
        s = s.rstrip("Z")
        if "." in s:
            s = s.split(".", 1)[0]
        if "+" in s:
            s = s.split("+", 1)[0]

        for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p"):
            try:
                return datetime.strptime(s, fmt).strftime("%H:%M")
            except ValueError:
                continue

        raise HTTPException(
            status_code=400,
            detail="Invalid draft date/time format. Expected audit_date='YYYY-MM-DD' and time='HH:MM'",
        )

    draft_date = (
        data.audit_date
        or (
            audit.actual_start_date.strftime("%Y-%m-%d")
            if audit.actual_start_date
            else None
        )
        or (
            audit.planned_start_date.strftime("%Y-%m-%d")
            if audit.planned_start_date
            else None
        )
    )
    draft_date = _normalize_draft_date(draft_date)

    normalized_start_time = (
        _normalize_draft_time(data.start_time) if data.start_time is not None else None
    )
    normalized_end_time = (
        _normalize_draft_time(data.end_time) if data.end_time is not None else None
    )

    # Empty strings from frontend autosave should be treated as "not provided".
    if (
        normalized_start_time is not None or normalized_end_time is not None
    ) and not draft_date:
        raise HTTPException(
            status_code=400,
            detail="audit_date is required when start_time or end_time is provided",
        )

    try:
        if normalized_start_time is not None:
            audit.actual_start_date = datetime.strptime(
                f"{draft_date} {normalized_start_time}", "%Y-%m-%d %H:%M"
            )
        if normalized_end_time is not None:
            audit.actual_end_date = datetime.strptime(
                f"{draft_date} {normalized_end_time}", "%Y-%m-%d %H:%M"
            )
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid draft date/time format. Expected audit_date='YYYY-MM-DD' and time='HH:MM'",
        )

    if data.strong_points is not None:
        audit.strong_points = data.strong_points
    if data.weak_points is not None:
        audit.weak_points = data.weak_points

    if data.answers is not None:
        existing_draft_answers = _get_draft_answers(db, audit_id)
        existing_draft_answer_ids = {a.id for a in existing_draft_answers}
        incoming_file_urls = {
            doc.file_url
            for ans in data.answers
            for doc in (ans.documents or [])
            if doc.file_url
        }

        if existing_draft_answer_ids:
            existing_draft_docs = (
                db.query(Document)
                .filter(Document.audit_answer_id.in_(existing_draft_answer_ids))
                .all()
            )
            existing_urls = {d.file_url for d in existing_draft_docs if d.file_url}
            removed_urls = existing_urls - incoming_file_urls
            for url in removed_urls:
                _maybe_delete_blob_if_unreferenced(db, url, existing_draft_answer_ids)

        # Match incoming answers to existing draft rows by raw question_id while
        # preserving order for duplicates (e.g. classification-mode rows).
        existing_by_qid: Dict[Optional[int], list[AuditAnswer]] = {}
        for existing in existing_draft_answers:
            existing_raw_qid = (
                existing.question_id
                if existing.question_id is not None
                else _extract_raw_question_id_from_draft_identifier(existing.identifier)
            )
            existing_by_qid.setdefault(existing_raw_qid, []).append(existing)

        kept_answer_ids: set[int] = set()

        for answer in data.answers:
            raw_qid = answer.question_id
            incoming_row_id = _sanitize_draft_row_id(answer.draft_row_id)
            db_question_id = raw_qid if (raw_qid is not None and raw_qid > 0) else None
            db_value = answer.value if answer.value is not None else -1
            encoded_finding = _encode_draft_finding_payload(
                answer.finding_text,
                answer.request_car,
                answer.car_reason,
            )

            matched_existing: Optional[AuditAnswer] = None
            if incoming_row_id:
                for bucket in existing_by_qid.values():
                    for i, candidate in enumerate(bucket):
                        if (
                            _extract_draft_row_id_from_identifier(candidate.identifier)
                            == incoming_row_id
                        ):
                            matched_existing = bucket.pop(i)
                            break
                    if matched_existing:
                        break
            if matched_existing is None:
                candidate_bucket = existing_by_qid.get(raw_qid, [])
                matched_existing = candidate_bucket.pop(0) if candidate_bucket else None

            if matched_existing is None:
                matched_existing = AuditAnswer(
                    audit_id=audit_id,
                    question_id=db_question_id,
                    value=db_value,
                    finding_text=encoded_finding,
                    fail=False,
                    improve=False,
                    pass_=False,
                    identifier=_build_draft_answer_identifier(raw_qid, incoming_row_id),
                    process=answer.process,
                    standard_paragraph=answer.standard_paragraph,
                    classification=answer.classification,
                    question_text=answer.question_text,
                    silent_box=bool(answer.silent_box),
                    created_at=now,
                )
                db.add(matched_existing)
                db.flush()
            else:
                matched_existing.question_id = db_question_id
                matched_existing.value = db_value
                matched_existing.finding_text = encoded_finding
                matched_existing.fail = False
                matched_existing.improve = False
                matched_existing.pass_ = False
                matched_existing.process = answer.process
                matched_existing.standard_paragraph = answer.standard_paragraph
                matched_existing.classification = answer.classification
                matched_existing.question_text = answer.question_text
                matched_existing.silent_box = bool(answer.silent_box)
                matched_existing.identifier = _build_draft_answer_identifier(
                    raw_qid,
                    incoming_row_id
                    or _extract_draft_row_id_from_identifier(
                        matched_existing.identifier
                    ),
                )

            kept_answer_ids.add(matched_existing.id)

            # Replace linked documents for this answer with incoming snapshot.
            existing_docs_for_answer = (
                db.query(Document)
                .filter(Document.audit_answer_id == matched_existing.id)
                .all()
            )
            for d in existing_docs_for_answer:
                db.delete(d)

            _create_documents_for_answer(
                db=db,
                audit_answer_id=matched_existing.id,
                documents=answer.documents,
                corrective_action_id=None,
            )

        # Remove draft rows no longer present in incoming payload.
        for existing in existing_draft_answers:
            if existing.id in kept_answer_ids:
                continue
            docs = (
                db.query(Document).filter(Document.audit_answer_id == existing.id).all()
            )
            for d in docs:
                db.delete(d)
            db.delete(existing)

    db.commit()
    db.refresh(audit)

    draft_answers_payload = _build_draft_answers_payload(db, audit_id)
    draft_etag = _compute_draft_etag(audit, draft_answers_payload)

    return {
        "audit_id": audit.id,
        "saved_at": now,
        "audit_date": audit.actual_start_date.strftime("%Y-%m-%d")
        if audit.actual_start_date
        else None,
        "start_time": audit.actual_start_date.strftime("%H:%M")
        if audit.actual_start_date
        else None,
        "end_time": audit.actual_end_date.strftime("%H:%M")
        if audit.actual_end_date
        else None,
        "strong_points": audit.strong_points,
        "weak_points": audit.weak_points,
        "answers": draft_answers_payload,
        "draft_etag": draft_etag,
    }


def get_audit_draft(audit_id: int, db: "Session") -> dict:
    """Return saved draft data so the UI can pre-fill fields on page load."""
    audit = db.query(Audit).filter(Audit.id == audit_id).first()
    if not audit:
        raise HTTPException(404, "Audit not found")

    draft_answers_payload = _build_draft_answers_payload(db, audit_id)
    draft_etag = _compute_draft_etag(audit, draft_answers_payload)

    return {
        "audit_id": audit.id,
        "saved_at": None,
        "audit_date": audit.actual_start_date.strftime("%Y-%m-%d")
        if audit.actual_start_date
        else None,
        "start_time": audit.actual_start_date.strftime("%H:%M")
        if audit.actual_start_date
        else None,
        "end_time": audit.actual_end_date.strftime("%H:%M")
        if audit.actual_end_date
        else None,
        "strong_points": audit.strong_points,
        "weak_points": audit.weak_points,
        "answers": draft_answers_payload,
        "draft_etag": draft_etag,
    }


PLANNING_STATUSES = ("planned", "rescheduled")


def get_planned_or_rescheduled_audits_by_auditor(auditor_id: int, db: Session):
    return (
        db.query(Audit)
        .filter(
            or_(
                Audit.auditor_id == auditor_id,
                Audit.second_auditor_id == auditor_id,
            ),
            Audit.status.in_(PLANNING_STATUSES),
        )
        .options(
            joinedload(Audit.auditees),
            joinedload(Audit.questionnaire).joinedload(Questionnaire.audit_type),
            joinedload(Audit.questionnaire).joinedload(Questionnaire.framework),
        )
        .order_by(asc(Audit.planned_start_date))
        .all()
    )


def getQuestionsByAudit(audit_id: int, db: Session):
    audit = (
        db.query(Audit)
        .filter(Audit.id == audit_id)
        .options(joinedload(Audit.questionnaire).joinedload(Questionnaire.questions))
        .first()
    )

    if not audit or not audit.questionnaire:
        return []

    return audit.questionnaire.questions


async def process_outlook_webhook_notification(notification: dict, db: Session):
    """
    Process a single Outlook webhook notification
    Handles event updates, reschedules, and cancellations
    """
    try:
        # Extract event ID from notification
        resource_data = notification.get("resourceData", {})
        event_id = resource_data.get("id")

        if not event_id:
            print("⚠️ No event ID in notification")
            return

        print(f"\n{'=' * 60}")
        print(f"{'=' * 60}")
        print(f"Event ID: {event_id}")

        # Get calendar owner via subscriptionId
        subscription_id = notification.get("subscriptionId")

        sub = (
            db.query(OutlookSubscription)
            .filter(OutlookSubscription.subscription_id == subscription_id)
            .first()
        )

        if not sub:
            print(f"⚠️ No subscription found for {subscription_id}")
            return

        calendar_owner_email = sub.user_email
        print(f"📧 Calendar Owner: {calendar_owner_email}")

        # Find audit associated with this event
        audit = db.query(Audit).filter(Audit.event_id == event_id).first()

        if not audit:
            print(f"ℹ️ Event {event_id} is not linked to any audit")
            print("   (This could be a personal calendar event - ignoring)")
            return

        print("📋 Audit Found:")
        print(f"   Number: #{audit.audit_number}")
        print(f"   ID: {audit.id}")
        print(f"   Status: {audit.status}")
        print(
            f"   Current Times: {audit.planned_start_date} → {audit.planned_end_date}"
        )

        # Fetch full event details from Graph API
        access_token = await get_access_token()
        event = await get_graph_event(event_id, access_token, calendar_owner_email)

        # Handle cancellation
        if event.get("isCancelled"):
            print("\n❌ Event is cancelled")
            await handle_event_cancellation(audit, db, event)
            db.commit()
            print(f"✅ Processed cancellation for audit #{audit.audit_number}")
            print(f"{'=' * 60}\n")
            return

        # Handle reschedule
        print("\n🔄 Checking for time changes...")
        await handle_event_reschedule(audit, event, db)

        # Optional: Track attendee changes
        # await handle_attendee_changes(audit, event, db)

        db.commit()
        print(f"\n✅ Successfully synced audit #{audit.audit_number} from Outlook")
        print(f"{'=' * 60}\n")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Webhook processing failed: {e}")
        traceback.print_exc()
        print(f"{'=' * 60}\n")
        raise


async def handle_event_reschedule(audit: Audit, event: dict, db: Session):
    """
    Handle time changes for an audit event

    Args:
        audit: The Audit database object
        event: Full event data from Graph API
        db: Database session
    """
    # Parse new times from event
    start_data = event.get("start", {})
    end_data = event.get("end", {})

    new_start_str = start_data.get("dateTime")
    new_end_str = end_data.get("dateTime")
    timezone_str = start_data.get("timeZone", "UTC")

    if not new_start_str or not new_end_str:
        print("⚠️ Missing start/end times in event")
        return

    # Convert to datetime
    try:
        # Clean the datetime string (remove microseconds beyond 6 digits)
        clean_start = new_start_str.split(".")[0]  # "2026-01-23T11:30:00"
        clean_end = new_end_str.split(".")[0]  # "2026-01-23T12:30:00"

        # Parse as naive datetime, then interpret it in the timezone Graph
        # reported (we always write our events with "UTC", but honor
        # whatever comes back instead of assuming) and convert down to the
        # naive-local convention used everywhere else in this app
        # (audit.planned_start_date / _as_utc / _to_utc_datetime all treat a
        # naive datetime as OUTLOOK_LOCAL_TIMEZONE). Without this step, the
        # UTC time coming back from Graph gets mistaken for local time,
        # audit.planned_start_date drifts by the UTC offset, and a spurious
        # "rescheduled" entry is logged every time Outlook echoes our own
        # create/update back through the webhook.
        try:
            graph_tz = ZoneInfo(timezone_str)
        except (ZoneInfoNotFoundError, ValueError):
            graph_tz = timezone.utc

        new_start = (
            datetime.fromisoformat(clean_start)
            .replace(tzinfo=graph_tz)
            .astimezone(ZoneInfo(OUTLOOK_LOCAL_TIMEZONE))
            .replace(tzinfo=None)
        )
        new_end = (
            datetime.fromisoformat(clean_end)
            .replace(tzinfo=graph_tz)
            .astimezone(ZoneInfo(OUTLOOK_LOCAL_TIMEZONE))
            .replace(tzinfo=None)
        )

        print("📅 Parsed times:")
        print(f"   Start: {new_start}")
        print(f"   End: {new_end}")
        print(f"   Timezone: {timezone_str}")

    except ValueError as e:
        print(f"❌ Failed to parse dates: {e}")
        print(f"   Start string: {new_start_str}")
        print(f"   End string: {new_end_str}")
        return

    # Check if times actually changed (comparing with current audit times)
    if audit.planned_start_date == new_start and audit.planned_end_date == new_end:
        print("ℹ️ No time change detected")
        return

    # Store both old times as ISO format in old_date column
    old_time_range = f"{audit.planned_start_date.isoformat()} to {audit.planned_end_date.isoformat()}"
    new_time_range = f"{new_start.isoformat()} to {new_end.isoformat()}"

    reschedule_entry = AuditRescheduleHistory(
        audit_id=audit.id,
        action_type="rescheduled",
        old_date=audit.planned_start_date,
        new_date=new_start,
        reason=f"Updated in Outlook Calendar. Old: {old_time_range}, New: {new_time_range}",
        changed_by=None,
        created_at=datetime.now(timezone.utc),
    )

    db.add(reschedule_entry)

    # Update audit
    audit.planned_start_date = new_start
    audit.planned_end_date = new_end
    audit.status = "rescheduled"

    print("✅ Audit rescheduled successfully")


async def handle_event_cancellation(
    audit: Audit, db: Session, event: Optional[dict] = None
):
    """
    Handle when an event is cancelled in Outlook

    Args:
        audit: The Audit database object
        event: Full event data from Graph API
        db: Database session
    """
    if audit.status == "cancelled":
        print("ℹ️ Audit already marked as cancelled")
        return

    print(f"❌ Cancelling audit #{audit.audit_number}")

    # Log the cancellation using YOUR schema
    cancellation_entry = AuditRescheduleHistory(
        audit_id=audit.id,
        action_type="postponed",
        old_date=audit.planned_start_date,
        new_date=None,
        reason="[cancelled] Event cancelled in Outlook Calendar",
        changed_by=None,
        created_at=datetime.now(timezone.utc),
    )

    db.add(cancellation_entry)

    # Update audit status
    audit.status = "cancelled"
    audit.event_created = False


def get_audit_answers(audit_id: int, db: Session, current_user: User):
    audit = db.query(Audit).filter(Audit.id == audit_id).first()
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    answers = (
        db.query(AuditAnswer)
        .options(
            joinedload(AuditAnswer.question),
            joinedload(AuditAnswer.documents),
        )
        .filter(AuditAnswer.audit_id == audit_id)
        .order_by(AuditAnswer.id)
        .all()
    )

    items: List[AuditAnswerOut] = []
    for ans in answers:
        docs = [
            DocumentItem(
                id=d.id,
                filename=d.filename,
                file_url=d.file_url,
                size=d.size,
                uploaded_at=d.uploaded_at.isoformat() if d.uploaded_at else None,
                document_type=getattr(d, "document_type", None) or "car_solution",
            )
            for d in (ans.documents or [])
        ]

        q = ans.question
        question_out = (
            QuestionOut(
                id=q.id,
                description=q.description,
                chapter=q.chapter,
                weight=q.weight,
                critical_value=q.critical_value,
                question_code=q.question_code,
                element=q.element,
                is_asterisk=q.is_asterisk,
            )
            if q
            else None
        )

        items.append(
            AuditAnswerOut(
                id=ans.id,
                identifier=ans.identifier,
                value=ans.value,
                finding_text=ans.finding_text,
                fail=ans.fail,
                improve=ans.improve,
                pass_=ans.pass_,
                process=ans.process,
                standard_paragraph=ans.standard_paragraph,
                classification=ans.classification,
                question_text=ans.question_text,
                silent_box=bool(ans.silent_box),
                created_at=ans.created_at.isoformat() if ans.created_at else None,
                question=question_out,
                documents=docs,
            )
        )

    if not can_view_silent_box(current_user):
        items = [item for item in items if not item.silent_box]

    return AuditAnswersResponse(
        audit_id=audit.id,
        audit_number=audit.audit_number,
        total_answers=len(items),
        total_pass=sum(1 for a in items if a.pass_),
        total_improve=sum(1 for a in items if a.improve),
        total_fail=sum(1 for a in items if a.fail),
        items=items,
    )
