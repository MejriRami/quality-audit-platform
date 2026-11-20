"""Auditor assistant: answers audit-methodology questions (VDA 6.3, IATF
16949, ISO 9001/14001, writing findings) and questions about the auditor's
own work - their audits, findings, open CARs and upcoming planned audits.

The auditee portal has its own CAR coach (chatbot_service.py); this one sits
behind the normal app login. Quality managers and admins get the same
assistant scoped to all audits instead of only their own.
"""

import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from openai import APIError, APITimeoutError
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.audit import Audit
from app.models.audit_answr import AuditAnswer
from app.models.audit_planning import AuditPlanItem, AuditPlanRun
from app.models.auditor_chatbot_message import AuditorChatbotMessage
from app.models.corrective_action import CorrectiveAction
from app.models.user import User
from app.services.ai.openai_client import (
    OPENAI_MAX_TOKENS,
    OPENAI_MODEL,
    OPENAI_TEMPERATURE,
    client as _client,
    create_chat_completion as _create_chat_completion,
)
from app.services.role_access_service import has_auditor_role, is_admin_or_quality_manager

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 20
MAX_MESSAGE_LENGTH = 4000
MAX_DAILY_MESSAGES = 100
RATE_LIMIT_SECONDS = 3

AUDIT_LOOKBACK_DAYS = 365
MAX_AUDITS = 40
MAX_OPEN_CARS = 40
MAX_FINDINGS = 30
MAX_PLAN_ITEMS = 20
TEXT_CLIP = 220

OPEN_CAR_STATUSES = ("pending", "rejected", "submitted")


def can_use_assistant(user: User) -> bool:
    return has_auditor_role(user) or is_admin_or_quality_manager(user)


def _clip(value, limit: int = TEXT_CLIP) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _day(value) -> str:
    if not value:
        return "-"
    return (value.date() if isinstance(value, datetime) else value).isoformat()


def _scope_label(global_scope: bool) -> str:
    return "all audits (quality manager / admin view)" if global_scope else "audits you lead"


def _audits_section(audits: list[Audit]) -> str:
    if not audits:
        return "No audits in the last 12 months or planned."
    lines = []
    for a in audits:
        questionnaire = getattr(a.questionnaire, "name", None) or "imported from Monday"
        score = f", score {float(a.total_score):.1f}" if a.total_score is not None else ""
        grade = f" ({a.result_class})" if a.result_class else ""
        lines.append(
            f"- {a.audit_number} | {a.plant or '-'} | {questionnaire} | status {a.status} | "
            f"planned {_day(a.planned_start_date)} | done {_day(a.actual_start_date)}{score}{grade}"
        )
    return "\n".join(lines)


def _cars_section(cars: list[CorrectiveAction], today: date) -> str:
    if not cars:
        return "No open corrective actions."
    lines = []
    for c in cars:
        late = " LATE" if c.due_date and c.due_date < today else ""
        owner = getattr(c.auditee, "email", None) or "-"
        finding = c.finding or getattr(c.answer, "finding_text", None) or c.reason_why
        lines.append(
            f"- {c.identifier or c.id} | audit {getattr(c.audit, 'audit_number', '-')} | "
            f"{getattr(c.audit, 'plant', '-')} | {c.status} | due {_day(c.due_date)}{late} | "
            f"owner {owner} | {c.action_type or 'corrective'} | finding: {_clip(finding)}"
        )
    return "\n".join(lines)


def _findings_section(answers: list[AuditAnswer]) -> str:
    if not answers:
        return "No failed or improvement findings on recent audits."
    lines = []
    for ans in answers:
        kind = "NC" if ans.fail else "improvement"
        label = ans.classification or kind
        where = ans.process or ans.standard_paragraph or ""
        lines.append(
            f"- {getattr(ans.audit, 'audit_number', '-')} | {label}"
            f"{' | ' + _clip(where, 60) if where else ''} | {_clip(ans.finding_text or ans.question_text)}"
        )
    return "\n".join(lines)


def _plan_section(items: list[AuditPlanItem]) -> str:
    if not items:
        return "No upcoming audits in the monthly plan."
    return "\n".join(
        f"- {_day(i.scheduled_date)} | {i.plant} | {i.product_line or '-'} | "
        f"{', '.join(i.trigger_codes or [])} | {i.checklist} | auditee {i.auditee_name or i.auditee_role}"
        for i in items
    )


def build_system_prompt(
    user: User,
    global_scope: bool,
    audits: list[Audit],
    open_cars: list[CorrectiveAction],
    findings: list[AuditAnswer],
    plan_items: list[AuditPlanItem],
    today: date,
) -> str:
    name = f"{user.first_name} {user.last_name}".strip()
    return f"""You are the audit assistant of the Northwind Audit Management app, talking to {name}. Today is {today.isoformat()}.

You help with two things:
1. Audit know-how: VDA 6.3 (process elements P1-P7, scoring 0/4/6/8/10, downgrading rules), IATF 16949, ISO 9001 and ISO 14001, how to prepare and run an audit, how to write a clear, evidence-based finding, how to classify it (major / minor nonconformity, observation, opportunity for improvement), and how to judge a corrective action (5 Whys, root cause vs symptom, containment vs permanent fix, effectiveness check).
2. Their own work, using ONLY the data below ({_scope_label(global_scope)}): which audits are coming up, which CARs are open or late, which findings keep repeating, what to prioritise.

Rules:
- Answer in the language the user writes in. Be concise and practical; use short lists and tables when they help.
- For questions about audits, CARs or findings, rely strictly on the data below. If the answer is not in it, say so - never invent audit numbers, dates, scores or owners.
- Quote standard clause numbers only when you are sure of them; otherwise describe the requirement without a number.
- You cannot change anything in the app. Point the user to the right screen instead (audits list, CAR review, audit planning).

## Audits (last 12 months and upcoming, newest first)
{_audits_section(audits)}

## Open corrective actions (oldest due date first)
{_cars_section(open_cars, today)}

## Recent nonconformities and improvement findings
{_findings_section(findings)}

## Upcoming audits in the monthly plan
{_plan_section(plan_items)}
"""


def _load_context(user: User, db: Session, today: date) -> dict:
    global_scope = is_admin_or_quality_manager(user)
    since = datetime.combine(today - timedelta(days=AUDIT_LOOKBACK_DAYS), datetime.min.time())

    audit_q = db.query(Audit).options(joinedload(Audit.questionnaire))
    if not global_scope:
        audit_q = audit_q.filter(Audit.auditor_id == user.id)
    audits = (
        audit_q.filter(Audit.planned_start_date >= since)
        .order_by(Audit.planned_start_date.desc())
        .limit(MAX_AUDITS)
        .all()
    )

    car_q = (
        db.query(CorrectiveAction)
        .join(Audit, Audit.id == CorrectiveAction.audit_id)
        .options(
            joinedload(CorrectiveAction.audit),
            joinedload(CorrectiveAction.auditee),
            joinedload(CorrectiveAction.answer),
        )
        .filter(CorrectiveAction.status.in_(OPEN_CAR_STATUSES))
    )
    if not global_scope:
        car_q = car_q.filter(Audit.auditor_id == user.id)
    open_cars = (
        car_q.order_by(CorrectiveAction.due_date.asc().nullslast())
        .limit(MAX_OPEN_CARS)
        .all()
    )

    finding_q = (
        db.query(AuditAnswer)
        .join(Audit, Audit.id == AuditAnswer.audit_id)
        .options(joinedload(AuditAnswer.audit))
        .filter(
            or_(AuditAnswer.fail.is_(True), AuditAnswer.improve.is_(True)),
            AuditAnswer.silent_box.is_(False),
            Audit.planned_start_date >= since,
        )
    )
    if not global_scope:
        finding_q = finding_q.filter(Audit.auditor_id == user.id)
    findings = (
        finding_q.order_by(Audit.planned_start_date.desc(), AuditAnswer.id)
        .limit(MAX_FINDINGS)
        .all()
    )

    plan_q = (
        db.query(AuditPlanItem)
        .join(AuditPlanRun)
        .filter(
            AuditPlanRun.status.in_(("draft", "approved")),
            AuditPlanItem.status == "scheduled",
            AuditPlanItem.scheduled_date >= today,
        )
    )
    if not global_scope:
        plan_q = plan_q.filter(AuditPlanItem.auditor_user_id == user.id)
    plan_items = plan_q.order_by(AuditPlanItem.scheduled_date).limit(MAX_PLAN_ITEMS).all()

    return {
        "global_scope": global_scope,
        "audits": audits,
        "open_cars": open_cars,
        "findings": findings,
        "plan_items": plan_items,
    }


def get_chat_history(user: User, db: Session) -> list[dict]:
    messages = (
        db.query(AuditorChatbotMessage)
        .filter_by(user_id=user.id)
        .order_by(AuditorChatbotMessage.created_at, AuditorChatbotMessage.id)
        .all()
    )
    return [{"role": m.role, "content": m.content, "created_at": m.created_at} for m in messages]


def clear_chat_history(user: User, db: Session) -> None:
    db.query(AuditorChatbotMessage).filter_by(user_id=user.id).delete()
    db.commit()


def _enforce_rate_limits(user: User, db: Session, now: datetime) -> None:
    last = (
        db.query(AuditorChatbotMessage)
        .filter_by(user_id=user.id)
        .order_by(AuditorChatbotMessage.created_at.desc(), AuditorChatbotMessage.id.desc())
        .first()
    )
    if last and (now - last.created_at).total_seconds() < RATE_LIMIT_SECONDS:
        raise HTTPException(status_code=429, detail="You're sending messages too quickly, please wait a moment.")
    daily = (
        db.query(AuditorChatbotMessage)
        .filter(
            AuditorChatbotMessage.user_id == user.id,
            AuditorChatbotMessage.created_at >= now - timedelta(hours=24),
        )
        .count()
    )
    if daily >= MAX_DAILY_MESSAGES:
        raise HTTPException(status_code=429, detail="Daily chat message limit reached, please try again tomorrow.")


def send_message(user: User, db: Session, message: str) -> dict:
    if not _client:
        raise HTTPException(status_code=503, detail="Chatbot is not configured")

    message = (message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    if len(message) > MAX_MESSAGE_LENGTH:
        raise HTTPException(
            status_code=400, detail=f"Message is too long (max {MAX_MESSAGE_LENGTH} characters)"
        )

    now = datetime.now(timezone.utc)
    _enforce_rate_limits(user, db, now)

    history = (
        db.query(AuditorChatbotMessage)
        .filter_by(user_id=user.id)
        .order_by(AuditorChatbotMessage.created_at, AuditorChatbotMessage.id)
        .all()
    )
    context = _load_context(user, db, now.date())
    chat_messages = [{"role": "system", "content": build_system_prompt(user, today=now.date(), **context)}]
    chat_messages += [{"role": m.role, "content": m.content} for m in history[-MAX_HISTORY_MESSAGES:]]
    chat_messages.append({"role": "user", "content": message})

    try:
        completion = _create_chat_completion({
            "model": OPENAI_MODEL,
            "messages": chat_messages,
            "max_completion_tokens": OPENAI_MAX_TOKENS,
            "temperature": OPENAI_TEMPERATURE,
        })
        reply = completion.choices[0].message.content
    except APITimeoutError:
        logger.error("OpenAI request timed out for auditor assistant user %s", user.id)
        raise HTTPException(status_code=504, detail="Chatbot timed out, please try again")
    except APIError:
        logger.exception("OpenAI request failed for auditor assistant user %s", user.id)
        raise HTTPException(status_code=502, detail="Chatbot is temporarily unavailable")

    # The reply must sort strictly after the question (see chatbot_service).
    db.add(AuditorChatbotMessage(user_id=user.id, role="user", content=message, created_at=now))
    db.add(AuditorChatbotMessage(
        user_id=user.id, role="assistant", content=reply, created_at=now + timedelta(microseconds=1)
    ))
    db.commit()
    return {"reply": reply}
