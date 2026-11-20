from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import os
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config.database import engine
from app.models.corrective_action import CorrectiveAction
from app.models.car_escalation import CarEscalation
from app.models.auditor_holiday import AuditorHoliday
from app.utils.send_car_email import send_email, get_or_create_car_token, build_car_form_url
from app.utils.build_car_followup_email import (
    build_auditee_reminder_email_body,
    build_plant_manager_email_body,
    build_group_vp_escalation_digest_email_body,
)

GROUP_VP_EMAIL = "jules.silva@example.com"
SMTP_FROM_EMAIL = os.getenv("SMTP_USER", GROUP_VP_EMAIL)


def _advisory_lock_key(name: str) -> int:
    """Stable bigint key for a Postgres advisory lock, derived from a job name."""
    digest = hashlib.sha256(name.encode()).digest()
    return int.from_bytes(digest[:8], "big", signed=True)


async def _run_locked(lock_name: str, coro_factory):
    """Run the coroutine returned by `coro_factory()` only if no other
    process is already running the same named job, using a Postgres
    session-level advisory lock on a dedicated connection (kept open for
    the whole call, independent of the ORM session's own commits/checkins).
    If a job with this name is already in progress elsewhere (e.g. an
    overlapping scheduler tick from another worker process), this returns
    None instead of running - that's what previously caused every
    escalation email to be sent twice: two processes both finding the same
    CARs eligible and both sending, before either had committed its dedup
    row. `coro_factory` (rather than an already-constructed coroutine) so
    nothing is created - let alone left un-awaited - when the lock isn't
    acquired.
    """
    lock_key = _advisory_lock_key(lock_name)
    lock_conn = engine.connect()
    try:
        acquired = lock_conn.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key}
        ).scalar()
        if not acquired:
            return None
        try:
            return await coro_factory()
        finally:
            lock_conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
    finally:
        lock_conn.close()

# A CAR stops needing overdue reminders/escalations once it's in any of these
# statuses. "submitted" is included because the auditee has already done
# their part (a solution is awaiting auditor review) - nagging them to
# "submit" again is wrong; only "rejected" sends it back into the pipeline.
CLOSED_STATUSES = ("accepted", "closed", "submitted")


def _days_overdue(due_date: date, today: date) -> int:
    return (today - due_date).days


def _get_auditor_holiday_dates(
    db: Session, auditor_id: int | None, cache: dict[int, set[date]]
) -> set[date]:
    """All calendar dates covered by any holiday period for this auditor."""
    if not auditor_id:
        return set()
    if auditor_id not in cache:
        periods = (
            db.query(AuditorHoliday)
            .filter(AuditorHoliday.user_id == auditor_id)
            .all()
        )
        days: set[date] = set()
        for period in periods:
            d = period.start_date
            while d <= period.end_date:
                days.add(d)
                d += timedelta(days=1)
        cache[auditor_id] = days
    return cache[auditor_id]


def _effective_overdue_days(
    due_date: date, today: date, holiday_dates: set[date]
) -> int:
    """Days overdue, excluding any day the responsible auditor was on holiday.

    This is what makes "on holiday" pause escalation rather than just delay
    the notification: a day spent on holiday never counts as overdue, so the
    clock doesn't jump forward the moment the auditor is back.
    """
    raw = (today - due_date).days
    if raw <= 0 or not holiday_dates:
        return raw
    excluded = sum(1 for d in holiday_dates if due_date < d <= today)
    return max(0, raw - excluded)


def _already_sent(db: Session, car_id: int, event_code: str) -> bool:
    return (
        db.query(CarEscalation)
        .filter(
            CarEscalation.corrective_action_id == car_id,
            CarEscalation.comment == event_code,
        )
        .first()
        is not None
    )


def _format_dt(dt_value: datetime | None) -> str:
    return dt_value.strftime("%d/%m/%Y %H:%M") if dt_value else "N/A"


def _build_immediate_action_email_body(
    *,
    audit_reference: str,
    auditee_name: str,
    car_identifier: str | None,
    due_label: str,
    plant: str,
    reason: str | None,
    stage: str = "warning",
) -> str:
    """
    stage:
      "warning"             -> sent BEFORE the 24h submission deadline, while there's
                                still time to act (proactive heads-up).
      "submission_overdue"  -> the 24h submission deadline has already passed.
      "closure_overdue"     -> the 48h closure deadline has already passed (plant manager).
    """
    if stage == "warning":
        title = "Immediate Action Required - Northwind"
        action_text = (
            "This corrective action was flagged as <strong>immediate action</strong> during the audit "
            "and must be submitted within 24 hours of the audit. The submission window is closing soon."
        )
    elif stage == "submission_overdue":
        title = "Immediate Action Overdue - Northwind"
        action_text = (
            "This corrective action was flagged as <strong>immediate action</strong> and its 24-hour "
            "submission window has now closed without a submission. Please act now to avoid further escalation."
        )
    else:  # closure_overdue
        title = "Immediate Action Escalation - Northwind"
        action_text = (
            "This corrective action's 48-hour immediate-action window has closed and it remains open. "
            "This has been escalated for your intervention."
        )

    return f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #1f2937; line-height: 1.6;">
        <div style="max-width: 720px; margin: 0 auto; padding: 24px;">
          <h2 style="color:#0f4c81;">{title}</h2>
          <p>Hello <strong>{auditee_name}</strong>,</p>
          <p>The corrective action <strong>{car_identifier or "N/A"}</strong> from audit <strong>{audit_reference}</strong> requires immediate action.</p>
          <p><strong>Plant:</strong> {plant}</p>
          <p><strong>Reason:</strong> {reason or "N/A"}</p>
          <p><strong>Deadline:</strong> {due_label}</p>
          <p>{action_text}</p>
          <p>Please log in to the application and complete the required action as soon as possible.</p>
        </div>
      </body>
    </html>
    """


def _determine_car_type(car: CorrectiveAction) -> str:
    answer = getattr(car, "answer", None)
    if not answer:
        return "Observation"
    if getattr(answer, "fail", False):
        return "Critical"
    if getattr(answer, "improve", False):
        return "Improvement"
    return "Observation"


def _car_row(
    car: CorrectiveAction, overdue_days: int, db: Session | None = None
) -> dict:
    answer = getattr(car, "answer", None)
    question = getattr(getattr(answer, "question", None), "description", None) if answer else None
    finding = car.finding or (getattr(answer, "finding_text", None) if answer else None) or getattr(car, "reason_why", None)
    row = {
        "question": question or "N/A",
        "finding": finding or "N/A",
        "due_date": car.due_date.strftime("%d/%m/%Y") if car.due_date else "N/A",
        "car_type": _determine_car_type(car),
        "days_overdue": overdue_days,
    }
    # Only the auditee-facing reminder needs a way to act on the CAR - plant
    # manager/VP escalations are informational, so `db` is passed only for
    # that call site.
    if db is not None:
        token = get_or_create_car_token(db, car)
        row["form_url"] = build_car_form_url(token)
    return row


def _group_eligible_cars(
    db: Session,
    overdue_cars: list[tuple[CorrectiveAction, int]],
    min_overdue: int,
    event_code: str,
) -> dict[tuple, list[tuple[CorrectiveAction, int]]]:
    """Group CARs still needing `event_code` by (audit, auditee, due date).

    CARs sharing the same audit, auditee and due date are bundled into a
    single email instead of one email per CAR.
    """
    groups: dict[tuple, list[tuple[CorrectiveAction, int]]] = defaultdict(list)
    for car, overdue_days in overdue_cars:
        if overdue_days < min_overdue or _already_sent(db, car.id, event_code):
            continue
        auditee_email = car.auditee.email if car.auditee else None
        if not auditee_email:
            continue
        key = (getattr(car.audit, "id", None), auditee_email, car.due_date)
        groups[key].append((car, overdue_days))
    return groups


def _car_row_with_audit(car: CorrectiveAction, overdue_days: int) -> dict:
    """Same as _car_row, plus the audit/plant/auditee identifiers - needed
    once a single email (the VP digest) can contain CARs from more than
    one audit, so each row has to carry its own context instead of relying
    on a shared per-email header."""
    row = _car_row(car, overdue_days)
    audit = car.audit
    row["audit_reference"] = audit.audit_number if audit else "N/A"
    row["plant"] = audit.plant if audit else "N/A"
    row["auditee_name"] = (car.auditee.email.split("@")[0] if car.auditee and car.auditee.email else "N/A")
    return row


def _group_eligible_cars_by_due_date(
    db: Session,
    overdue_cars: list[tuple[CorrectiveAction, int]],
    min_overdue: int,
    event_code: str,
) -> dict[date, list[tuple[CorrectiveAction, int]]]:
    """Group CARs still needing `event_code` by due date ALONE, regardless
    of audit or auditee. Unlike the other escalation stages, the VP is one
    fixed recipient across every audit, so there's no reason to fragment
    their inbox into one email per audit the way _group_eligible_cars does
    for the auditee/plant-manager stages (where the recipient genuinely
    differs per audit)."""
    groups: dict[date, list[tuple[CorrectiveAction, int]]] = defaultdict(list)
    for car, overdue_days in overdue_cars:
        if overdue_days < min_overdue or _already_sent(db, car.id, event_code):
            continue
        if not (car.auditee and car.auditee.email):
            continue
        groups[car.due_date].append((car, overdue_days))
    return groups


async def process_car_followups(db: Session) -> dict:
    """Public entry point - see _run_locked. Only one process can run the
    actual followup logic at a time; an overlapping call is skipped
    rather than duplicating every email it would have sent."""
    result = await _run_locked(
        "car_escalation_service.process_car_followups", lambda: _process_car_followups(db)
    )
    if result is None:
        return {
            "skipped": True,
            "reason": "another process_car_followups run is already in progress",
            "open_cars_checked": 0,
            "auditee_reminders_sent": 0,
            "plant_manager_emails_sent": 0,
            "group_vp_emails_sent": 0,
        }
    return result


async def _process_car_followups(db: Session) -> dict:
    today = date.today()

    open_cars = db.query(CorrectiveAction).filter(
        CorrectiveAction.due_date != None,
        ~CorrectiveAction.status.in_(CLOSED_STATUSES),
    ).all()

    holiday_cache: dict[int, set[date]] = {}

    # Days 1..8 => nothing. Keep only CARs overdue by 9+ days, with their
    # overdue day count pre-computed (holiday-adjusted).
    overdue_cars: list[tuple[CorrectiveAction, int]] = []
    for car in open_cars:
        if not car.due_date:
            continue
        holiday_dates = _get_auditor_holiday_dates(
            db, getattr(car.audit, "auditor_id", None) if car.audit else None, holiday_cache
        )
        overdue_days = _effective_overdue_days(car.due_date, today, holiday_dates)
        if overdue_days < 9:
            continue
        overdue_cars.append((car, overdue_days))

    async def _send_group(
        *,
        event_code: str,
        min_overdue: int,
        recipient_fn,
        cc_fn,
        subject_fn,
        body_fn,
        mark_escalated: bool = False,
        include_form_link: bool = False,
    ) -> int:
        groups = _group_eligible_cars(db, overdue_cars, min_overdue, event_code)
        sent = 0
        for (_audit_id, auditee_email, due_date), items in groups.items():
            car0 = items[0][0]
            audit = car0.audit
            auditee_name = auditee_email.split("@")[0]
            plant_manager_email = getattr(audit, "supervisor_email", None) if audit else None
            auditor_email = getattr(getattr(audit, "auditor", None), "email", None) if audit else None
            audit_reference = audit.audit_number if audit else "N/A"
            plant = audit.plant if audit else "N/A"
            due_date_str = due_date.strftime("%d/%m/%Y") if due_date else "N/A"

            recipient = recipient_fn(auditee_email, plant_manager_email)
            if not recipient:
                continue

            cars_data = [
                _car_row(car, overdue_days, db=db if include_form_link else None)
                for car, overdue_days in items
            ]

            await send_email(
                subject=subject_fn(audit_reference, len(items)),
                recipients=[recipient],
                cc=cc_fn(auditee_email, plant_manager_email),
                body_html=body_fn(
                    audit_reference=audit_reference,
                    due_date=due_date_str,
                    auditee_name=auditee_name,
                    plant=plant,
                    cars=cars_data,
                ),
                sender_email=SMTP_FROM_EMAIL,
                sender_name="Northwind",
                reply_to=auditor_email,
                db=db,                      # FIX: pass db so delivery is tracked
                context="car_escalation",   # FIX: add context for email_deliveries log
            )

            for car, _overdue_days in items:
                if mark_escalated:
                    car.escalated = True
                db.add(CarEscalation(
                    corrective_action_id=car.id,
                    escalated_at=datetime.utcnow(),
                    email_sent_to=recipient,
                    comment=event_code,
                ))
            sent += len(items)
        return sent

    # Day 9 / Day 10 => reminders to auditee
    # FIX: >= instead of == so CARs created already overdue still receive
    #      these reminders on first run
    auditee_reminders_sent = await _send_group(
        event_code="DAY_9_AUDITEE_REMINDER",
        min_overdue=9,
        recipient_fn=lambda auditee_email, plant_manager_email: auditee_email,
        cc_fn=lambda auditee_email, plant_manager_email: None,
        subject_fn=lambda ref, n: f"Reminder - {n} CAR(s) overdue (Day 9) ({ref})" if n > 1 else f"Reminder - CAR overdue (Day 9) ({ref})",
        body_fn=build_auditee_reminder_email_body,
        include_form_link=True,
    )
    auditee_reminders_sent += await _send_group(
        event_code="DAY_10_AUDITEE_REMINDER",
        min_overdue=10,
        recipient_fn=lambda auditee_email, plant_manager_email: auditee_email,
        cc_fn=lambda auditee_email, plant_manager_email: None,
        subject_fn=lambda ref, n: f"Reminder - {n} CAR(s) overdue (Day 10) ({ref})" if n > 1 else f"Reminder - CAR overdue (Day 10) ({ref})",
        body_fn=build_auditee_reminder_email_body,
        include_form_link=True,
    )

    # Day 11 => escalation to plant manager
    plant_manager_emails_sent = await _send_group(
        event_code="DAY_11_PLANT_MANAGER",
        min_overdue=11,
        recipient_fn=lambda auditee_email, plant_manager_email: plant_manager_email,
        cc_fn=lambda auditee_email, plant_manager_email: [auditee_email] if auditee_email else None,
        subject_fn=lambda ref, n: f"Escalation - {n} CAR(s) still open at day 11 ({ref})" if n > 1 else f"Escalation - CAR still open at day 11 ({ref})",
        body_fn=build_plant_manager_email_body,
    )

    # Day 15 => escalation digest to Group VP. Unlike the other stages, the
    # VP is a single fixed recipient across every audit, so ALL CARs that
    # hit day 15 are bundled together (grouped by due date) instead of one
    # email per audit - the VP gets one digest per due date, not N separate
    # emails for N different audits.
    group_vp_emails_sent = 0
    vp_groups = _group_eligible_cars_by_due_date(db, overdue_cars, 15, "DAY_15_GROUP_VP")
    for due_date, items in vp_groups.items():
        due_date_str = due_date.strftime("%d/%m/%Y") if due_date else "N/A"
        cars_data = [_car_row_with_audit(car, overdue_days) for car, overdue_days in items]

        cc_emails: list[str] = []
        seen_cc: set[str] = set()
        for car, _overdue_days in items:
            for email in (
                getattr(car.audit, "supervisor_email", None) if car.audit else None,
                car.auditee.email if car.auditee else None,
            ):
                if email and email.lower() not in seen_cc:
                    seen_cc.add(email.lower())
                    cc_emails.append(email)

        audits_count = len({getattr(car.audit, "id", None) for car, _overdue_days in items})
        subject = (
            f"Escalation - {len(items)} CAR(s) across {audits_count} audit(s) still open at day 15 ({due_date_str})"
            if audits_count > 1
            else f"Escalation - {len(items)} CAR(s) still open at day 15 ({due_date_str})"
        )

        await send_email(
            subject=subject,
            recipients=[GROUP_VP_EMAIL],
            cc=cc_emails or None,
            body_html=build_group_vp_escalation_digest_email_body(due_date=due_date_str, cars=cars_data),
            sender_email=SMTP_FROM_EMAIL,
            sender_name="Northwind",
            db=db,
            context="car_escalation",
        )

        for car, _overdue_days in items:
            car.escalated = True
            db.add(CarEscalation(
                corrective_action_id=car.id,
                escalated_at=datetime.utcnow(),
                email_sent_to=GROUP_VP_EMAIL,
                comment="DAY_15_GROUP_VP",
            ))
        group_vp_emails_sent += len(items)

    db.commit()

    return {
        "open_cars_checked": len(open_cars),
        "auditee_reminders_sent": auditee_reminders_sent,
        "plant_manager_emails_sent": plant_manager_emails_sent,
        "group_vp_emails_sent": group_vp_emails_sent,
    }


async def process_immediate_action_followups(db: Session) -> dict:
    """Public entry point - see _run_locked. Same overlapping-process
    protection as process_car_followups."""
    result = await _run_locked(
        "car_escalation_service.process_immediate_action_followups",
        lambda: _process_immediate_action_followups(db),
    )
    if result is None:
        return {
            "skipped": True,
            "reason": "another process_immediate_action_followups run is already in progress",
            "open_cars_checked": 0,
            "immediate_12h_warnings_sent": 0,
            "immediate_24h_reminders_sent": 0,
            "immediate_48h_escalations_sent": 0,
        }
    return result


async def _process_immediate_action_followups(db: Session) -> dict:
    # submission_due_at / closure_due_at are TIMESTAMP(timezone=True) columns
    # (set from datetime.now(timezone.utc) at CAR creation), so `now` must be
    # tz-aware too - comparing against a naive datetime.utcnow() raises a
    # TypeError and would silently abort this whole job.
    now = datetime.now(timezone.utc)
    open_cars = (
        db.query(CorrectiveAction)
        .filter(
            CorrectiveAction.immediate_action_required.is_(True),
            CorrectiveAction.status == "pending",
        )
        .all()
    )

    warning_sent = 0
    reminder_24h_sent = 0
    escalation_48h_sent = 0

    for car in open_cars:
        audit = car.audit
        if not audit:
            continue

        auditee_email = car.auditee.email if car.auditee else None
        auditor_email = getattr(getattr(audit, "auditor", None), "email", None)
        plant_manager_email = getattr(audit, "supervisor_email", None) if audit else None
        audit_reference = audit.audit_number if audit else "N/A"
        plant = audit.plant if audit else "N/A"
        reason = getattr(car, "reason_why", None)
        auditee_name = (
            car.auditee.email.split("@")[0]
            if car.auditee and car.auditee.email
            else "Auditee"
        )

        # Proactive warning, sent once the submission window is at its halfway
        # point but before it actually closes - this is the only email that
        # reaches the auditee while there's still time to act.
        if car.submission_due_at:
            warning_at = car.submission_due_at - timedelta(hours=12)
            event_code = "IMMEDIATE_ACTION_12H_WARNING"
            if (
                warning_at <= now < car.submission_due_at
                and auditee_email
                and not _already_sent(db, car.id, event_code)
            ):
                await send_email(
                    subject=f"Immediate action required - CAR {car.identifier or car.id}",
                    recipients=[auditee_email],
                    cc=[auditor_email] if auditor_email else None,
                    body_html=_build_immediate_action_email_body(
                        audit_reference=audit_reference,
                        auditee_name=auditee_name,
                        car_identifier=car.identifier,
                        due_label=_format_dt(car.submission_due_at),
                        plant=plant,
                        reason=reason,
                        stage="warning",
                    ),
                    sender_email=SMTP_FROM_EMAIL,
                    sender_name="Northwind",
                    reply_to=auditor_email,
                )
                db.add(
                    CarEscalation(
                        corrective_action_id=car.id,
                        escalated_at=datetime.utcnow(),
                        email_sent_to=auditee_email,
                        comment=event_code,
                    )
                )
                warning_sent += 1

        if car.submission_due_at and now >= car.submission_due_at:
            event_code = "IMMEDIATE_ACTION_24H_REMINDER"
            if auditee_email and not _already_sent(db, car.id, event_code):
                await send_email(
                    subject=f"Immediate action overdue - CAR {car.identifier or car.id}",
                    recipients=[auditee_email],
                    cc=[auditor_email] if auditor_email else None,
                    body_html=_build_immediate_action_email_body(
                        audit_reference=audit_reference,
                        auditee_name=auditee_name,
                        car_identifier=car.identifier,
                        due_label=_format_dt(car.submission_due_at),
                        plant=plant,
                        reason=reason,
                        stage="submission_overdue",
                    ),
                    sender_email=SMTP_FROM_EMAIL,
                    sender_name="Northwind",
                    reply_to=auditor_email,
                )
                db.add(
                    CarEscalation(
                        corrective_action_id=car.id,
                        escalated_at=datetime.utcnow(),
                        email_sent_to=auditee_email,
                        comment=event_code,
                    )
                )
                reminder_24h_sent += 1

        if car.closure_due_at and now >= car.closure_due_at:
            event_code = "IMMEDIATE_ACTION_48H_ESCALATION"
            if plant_manager_email and not _already_sent(db, car.id, event_code):
                cc_list = [email for email in [auditee_email, auditor_email] if email]
                await send_email(
                    subject=f"Immediate action escalation - CAR {car.identifier or car.id}",
                    recipients=[plant_manager_email],
                    cc=cc_list if cc_list else None,
                    body_html=_build_immediate_action_email_body(
                        audit_reference=audit_reference,
                        auditee_name=auditee_name,
                        car_identifier=car.identifier,
                        due_label=_format_dt(car.closure_due_at),
                        plant=plant,
                        reason=reason,
                        stage="closure_overdue",
                    ),
                    sender_email=SMTP_FROM_EMAIL,
                    sender_name="Northwind",
                    reply_to=auditor_email,
                )
                db.add(
                    CarEscalation(
                        corrective_action_id=car.id,
                        escalated_at=datetime.utcnow(),
                        email_sent_to=plant_manager_email,
                        comment=event_code,
                    )
                )
                escalation_48h_sent += 1

    db.commit()
    return {
        "open_cars_checked": len(open_cars),
        "immediate_12h_warnings_sent": warning_sent,
        "immediate_24h_reminders_sent": reminder_24h_sent,
        "immediate_48h_escalations_sent": escalation_48h_sent,
    }
