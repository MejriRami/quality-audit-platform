"""Generate, review, approve and complete monthly audit plans.

Lifecycle: generate -> draft run (a newer draft supersedes older ones for the
same month) -> reviewer edits items -> approve (one approved run per month)
-> each audit is marked completed, which writes audit_plan_audit_history so
next month's "audited in the last N months" checks see it.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import cast
from sqlalchemy.orm import Session
from sqlalchemy.types import Date

from app.config.database import SessionLocal
from app.models.audit import Audit
from app.models.audit_planning import (
    AuditPlanAuditHistory,
    AuditPlanItem,
    AuditPlanRun,
)
from app.models.plant_holiday import PlantHoliday
from app.models.user import User
from app.services.audit_planning import rules, sources
from app.services.audit_planning.auditees import OVERRIDDEN, AuditeeResolver
from app.services.role_access_service import has_auditor_role

logger = logging.getLogger(__name__)

MAX_AUDITS_PER_AUDITOR_PER_DAY = 2

EDITABLE_STATUSES = {
    rules.STATUS_SCHEDULED,
    rules.STATUS_OVER_CAPACITY,
    rules.STATUS_SUPPRESSED_RECENT,
    "removed",
}


class PlanError(Exception):
    """A request the plan rules don't allow; the router maps it to 409."""


def _active_runs_filter():
    return AuditPlanRun.status.in_(("draft", "approved"))


# ─────────────────────────────────────────────────────────────
# Generate
# ─────────────────────────────────────────────────────────────


def _plant_holidays(db: Session, plan_month: date) -> dict[str, set[date]]:
    first, last = rules.month_bounds(plan_month)
    out: dict[str, set[date]] = {}
    for h in db.query(PlantHoliday).filter(PlantHoliday.holiday_date.between(first, last)):
        plant = rules.normalize_plant(h.plant)
        if plant:
            out.setdefault(plant, set()).add(h.holiday_date)
    return out


def generate_plan(
    db: Session,
    plan_month: date,
    *,
    user_id: Optional[int] = None,
    as_of: Optional[date] = None,
) -> AuditPlanRun:
    plan_month = plan_month.replace(day=1)
    as_of = as_of or date.today()
    if rules.month_bounds(plan_month)[1] < as_of:
        raise PlanError("Cannot plan a month that has already ended.")
    approved = (
        db.query(AuditPlanRun)
        .filter(AuditPlanRun.plan_month == plan_month, AuditPlanRun.status == "approved")
        .first()
    )
    if approved:
        raise PlanError(f"The plan for {plan_month:%B %Y} is already approved (run #{approved.id}).")

    facts = sources.build_facts(db, plan_month, as_of)
    evaluation = rules.evaluate(facts)
    rules.apply_recent_line_audit_rule(evaluation.candidates, facts.history, as_of)
    rules.schedule(
        evaluation.candidates,
        plan_month,
        holidays=_plant_holidays(db, plan_month),
        not_before=as_of,
    )

    warnings = list(evaluation.warnings)
    warnings += [
        reason
        for key, reason in facts.unavailable_reasons.items()
        if key != "metrics_partial"
    ]

    for old in db.query(AuditPlanRun).filter(
        AuditPlanRun.plan_month == plan_month, AuditPlanRun.status == "draft"
    ):
        old.status = "superseded"

    run = AuditPlanRun(
        plan_month=plan_month,
        status="draft",
        as_of=as_of,
        check_status=evaluation.check_status,
        warnings=warnings,
        generated_by_user_id=user_id,
    )
    resolver = AuditeeResolver(db)
    for cand in evaluation.candidates:
        auditee = resolver.resolve(cand)
        run.items.append(
            AuditPlanItem(
                plant=cand.plant,
                product_line=cand.product_line,
                project_code=cand.project_code,
                support_process_id=cand.support_process_id,
                trigger_codes=cand.trigger_codes,
                checklist=cand.checklist,
                history_kind=cand.history_kind,
                evidence=cand.evidence,
                complaint_volume=cand.complaint_volume,
                priority=cand.priority,
                status=cand.status,
                status_reason=cand.status_reason,
                scheduled_date=cand.scheduled_date,
                auditee_role=cand.auditee_role,
                auditee_name=auditee.name,
                auditee_email=auditee.email,
                auditee_status=auditee.status,
                auditee_note=auditee.note,
            )
        )
    db.add(run)
    db.commit()
    db.refresh(run)
    logger.info(
        "audit planning: run #%s for %s - %s items, %s warnings",
        run.id, plan_month, len(run.items), len(warnings),
    )
    return run


def run_monthly_plan_job() -> None:
    """Scheduler entry point: draft the plan for the current month on the 1st,
    once last month's data is complete."""
    db = SessionLocal()
    try:
        generate_plan(db, date.today().replace(day=1))
    except PlanError as exc:
        logger.info("audit planning job skipped: %s", exc)
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("audit planning job failed")
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────
# Review / override
# ─────────────────────────────────────────────────────────────


def _check_capacity(
    db: Session, item: AuditPlanItem, day: date, auditor_id: Optional[int]
) -> None:
    others = (
        db.query(AuditPlanItem)
        .join(AuditPlanRun)
        .filter(
            _active_runs_filter(),
            AuditPlanItem.id != item.id,
            AuditPlanItem.status.in_((rules.STATUS_SCHEDULED, "completed")),
            AuditPlanItem.scheduled_date == day,
        )
        .all()
    )
    app_audits = (
        db.query(Audit)
        .filter(cast(Audit.planned_start_date, Date) == day, Audit.status != "cancelled")
        .all()
    )
    if auditor_id:
        mine = sum(1 for o in others if o.auditor_user_id == auditor_id)
        mine += sum(1 for a in app_audits if a.auditor_id == auditor_id)
        if mine >= MAX_AUDITS_PER_AUDITOR_PER_DAY:
            raise PlanError(
                f"This auditor already has {MAX_AUDITS_PER_AUDITOR_PER_DAY} audits on {day:%a %d %b}."
            )


def update_item(db: Session, item_id: int, changes: dict, user: User) -> AuditPlanItem:
    item = db.get(AuditPlanItem, item_id)
    if not item:
        raise LookupError("Plan item not found.")
    if item.run.status == "superseded":
        raise PlanError("This plan was superseded by a newer run.")
    if item.status == "completed":
        raise PlanError("Completed audits can't be edited.")

    status = changes.get("status", item.status)
    if status not in EDITABLE_STATUSES:
        raise PlanError(f"Status must be one of: {', '.join(sorted(EDITABLE_STATUSES))}.")
    day = changes["scheduled_date"] if "scheduled_date" in changes else item.scheduled_date
    auditor_id = changes["auditor_user_id"] if "auditor_user_id" in changes else item.auditor_user_id

    if auditor_id:
        auditor = db.get(User, auditor_id)
        if not auditor or not auditor.active or not has_auditor_role(auditor):
            raise PlanError("Selected user is not an active auditor.")

    if status == rules.STATUS_SCHEDULED:
        if not day:
            raise PlanError("A scheduled audit needs a date.")
        first, last = rules.month_bounds(item.run.plan_month)
        if not first <= day <= last:
            raise PlanError(f"Date must be within {first:%B %Y}.")
        if (
            status != item.status
            or day != item.scheduled_date
            or auditor_id != item.auditor_user_id
        ):
            _check_capacity(db, item, day, auditor_id)

    item.status = status
    item.scheduled_date = day if status == rules.STATUS_SCHEDULED else None
    item.auditor_user_id = auditor_id
    if "auditee_name" in changes or "auditee_email" in changes:
        item.auditee_name = changes.get("auditee_name", item.auditee_name)
        item.auditee_email = (changes.get("auditee_email", item.auditee_email) or "").strip().lower() or None
        item.auditee_status = OVERRIDDEN
    if "override_note" in changes:
        item.override_note = changes["override_note"]
    item.overridden = True
    item.updated_by_user_id = user.id
    db.commit()
    db.refresh(item)
    return item


def approve_run(db: Session, run_id: int, user: User) -> AuditPlanRun:
    run = db.get(AuditPlanRun, run_id)
    if not run:
        raise LookupError("Plan run not found.")
    if run.status != "draft":
        raise PlanError(f"Only a draft plan can be approved (this one is {run.status}).")
    missing = [
        f"#{i.id} {i.plant}"
        for i in run.items
        if i.status == rules.STATUS_SCHEDULED and (not i.auditor_user_id or not i.auditee_email)
    ]
    if missing:
        raise PlanError(
            "Every scheduled audit needs an auditor and an auditee email before approval: "
            + ", ".join(missing)
        )
    run.status = "approved"
    run.approved_at = datetime.now(timezone.utc)
    run.approved_by_user_id = user.id
    db.commit()
    db.refresh(run)
    return run


def complete_item(db: Session, item_id: int, completed_on: date, user: User) -> AuditPlanItem:
    item = db.get(AuditPlanItem, item_id)
    if not item:
        raise LookupError("Plan item not found.")
    if item.run.status != "approved":
        raise PlanError("Only audits in an approved plan can be completed.")
    if item.status != rules.STATUS_SCHEDULED:
        raise PlanError("Only scheduled audits can be completed.")
    if completed_on > date.today():
        raise PlanError("Completion date can't be in the future.")

    item.status = "completed"
    item.completed_on = completed_on
    item.updated_by_user_id = user.id
    db.add(
        AuditPlanAuditHistory(
            plant=item.plant,
            product_line=item.product_line,
            kind=item.history_kind,
            support_process_id=item.support_process_id,
            audited_on=completed_on,
            source="plan",
            plan_item_id=item.id,
            created_by_user_id=user.id,
        )
    )
    db.commit()
    db.refresh(item)
    return item
