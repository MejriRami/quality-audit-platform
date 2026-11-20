"""Builds rules.Facts from the source systems.

Every loader returns data or raises; build_facts() turns a failure into
facts.<source> = None plus a reason, so the affected checks show up as
"not evaluated" on the plan instead of silently passing.

Source systems - same server and user as this app's DATABASE_URL, only the
database name differs (each can be overridden with its own env var):
- complaints/8D DB   problem_solving_app_db          COMPLAINTS_DATABASE_URL
- projects/APQP DB   APQP_DB                         PROJECTS_DATABASE_URL
- certifications DB  "Audit external certification"  CERTIFICATIONS_DATABASE_URL
- roles MCP          PPM KPI results (P11)
- this app's DB      manual inputs + completed-audit history
All source connections are opened read-only.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import date
from functools import lru_cache
from statistics import mean
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session

from app.config.database import DATABASE_URL

from app.models.audit_planning import (
    AuditPlanAuditHistory,
    AuditPlanCustomerEscalation,
    AuditPlanQualityMetric,
    AuditPlanSupportProcess,
)
from app.services.audit_planning import rules
from app.services.org_member_directory import _call_mcp_tool

logger = logging.getLogger(__name__)

# Roles-MCP KPI ids for PPM (both "lower is better", weekly results per plant).
PPM_KPIS = {588: "ppm_external", 589: "ppm_internal"}


class SourceUnavailable(Exception):
    pass


SOURCE_DATABASES = {
    "COMPLAINTS_DATABASE_URL": "problem_solving_app_db",
    "PROJECTS_DATABASE_URL": "APQP_DB",
    "CERTIFICATIONS_DATABASE_URL": "Audit external certification",
}


@lru_cache(maxsize=None)
def _readonly_engine(env_var: str) -> Engine:
    url = os.getenv(env_var) or make_url(DATABASE_URL).set(database=SOURCE_DATABASES[env_var])
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        connect_args={"options": "-c default_transaction_read_only=on -c statement_timeout=30000"},
    )


# ─────────────────────────────────────────────────────────────
# Complaints DB
# ─────────────────────────────────────────────────────────────

# Open complaints (closed_at IS NULL - the live `status` holds the 8D step,
# D1..D8), plus anything opened in the ranking window or closed recently
# enough to have been closed late last month.
COMPLAINTS_SQL = text(
    """
    SELECT c.id, c.reference_number, c.northwind_plant::text AS plant,
           c.product_line::text AS product_line, c.status, c.customer,
           c.defects, c.complaint_opening_date, c.due_date, c.closed_at,
           EXISTS (
               SELECT 1 FROM reports r
               JOIN report_steps s ON s.report_id = r.id
               WHERE r.complaint_id = c.id
                 AND s.completed_at IS NULL
                 AND (s.is_overdue OR s.due_date < now())
           ) AS has_overdue_step
    FROM complaints c
    WHERE c.closed_at IS NULL
       OR c.complaint_opening_date >= :since
       OR c.closed_at >= :closed_since
    """
)


def load_complaints(as_of: date, lookback_start: date) -> list[rules.Complaint]:
    since = rules.add_months(as_of, -rules.VOLUME_WINDOW_MONTHS)
    with _readonly_engine("COMPLAINTS_DATABASE_URL").connect() as conn:
        rows = conn.execute(
            COMPLAINTS_SQL, {"since": since, "closed_since": lookback_start}
        ).mappings().all()
    return [
        rules.Complaint(
            id=r["id"],
            reference=r["reference_number"],
            plant=rules.normalize_plant(r["plant"]),
            product_line=rules.normalize_product_line(r["product_line"]),
            status=(r["status"] or "").strip().lower(),
            opening_date=r["complaint_opening_date"],
            due_date=r["due_date"],
            closed_at=r["closed_at"],
            has_overdue_step=bool(r["has_overdue_step"]),
            customer=r["customer"],
            defect=r["defects"],
        )
        for r in rows
    ]


# ─────────────────────────────────────────────────────────────
# Projects / APQP DB
# ─────────────────────────────────────────────────────────────

# SOP = planned date when set, otherwise the target date; projects that have
# already reached SOP (sop_actual_date set) or are closed/cancelled are skipped.
# Only APQP projects qualify for P6: the Monday "Project Sales Category" is
# "APQP Project", or the project category itself names APQP (e.g. "APQP",
# "Tianjin Project Category - Major Change APQP"). Mass Production, Sample,
# Tooling and CIP projects are excluded even when their SOP is in the window.
PROJECTS_SQL = text(
    """
    SELECT project_code, name, plant, product_line, project_manager,
           project_manager_email,
           COALESCE(sop_planned_date, sop_target_date) AS sop_date
    FROM projects
    WHERE is_archived IS NOT TRUE
      AND sop_actual_date IS NULL
      AND lower(COALESCE(project_status, '')) NOT IN ('closed', 'cancelled', 'canceled')
      AND (
          raw_monday_data->>'Project Sales Category' ILIKE '%apqp%'
          OR project_category ILIKE '%apqp%'
      )
      AND COALESCE(sop_planned_date, sop_target_date) BETWEEN :start AND :end
    """
)


def load_projects(as_of: date) -> list[rules.Project]:
    end = rules.add_months(as_of, rules.SOP_HORIZON_MONTHS)
    with _readonly_engine("PROJECTS_DATABASE_URL").connect() as conn:
        rows = conn.execute(PROJECTS_SQL, {"start": as_of, "end": end}).mappings().all()
    return [
        rules.Project(
            code=r["project_code"],
            name=r["name"],
            plant=rules.normalize_plant(r["plant"]),
            product_line=rules.normalize_product_line(r["product_line"]),
            sop_date=r["sop_date"],
            manager_name=r["project_manager"],
            manager_email=(r["project_manager_email"] or "").strip().lower() or None,
        )
        for r in rows
    ]


# ─────────────────────────────────────────────────────────────
# Certifications DB (P8 / P10)
# ─────────────────────────────────────────────────────────────


# certifications keeps one row per audit (validated or pending_review, plus
# duplicates), so rules.pick_next_external_audit chooses the date per plant
# and standard. Rejected rows are ignored.
CERTIFICATIONS_SQL = text(
    """
    SELECT plant, status::text AS status, next_expected_audit AS next_audit,
           CASE WHEN certification_type ILIKE '%16949%' THEN 'IATF16949'
                WHEN certification_type ILIKE '%14001%' THEN 'ISO14001' END AS standard
    FROM certifications
    WHERE status::text <> 'rejected'
      AND next_expected_audit IS NOT NULL
      AND (certification_type ILIKE '%16949%' OR certification_type ILIKE '%14001%')
    """
)


def load_external_audits(as_of: date) -> dict[str, dict[str, Optional[date]]]:
    """plant -> {"IATF16949": next external audit date, "ISO14001": ...}."""
    with _readonly_engine("CERTIFICATIONS_DATABASE_URL").connect() as conn:
        rows = conn.execute(CERTIFICATIONS_SQL).mappings().all()
    grouped: dict[tuple[str, str], list[tuple[str, date]]] = {}
    for r in rows:
        plant = rules.normalize_plant(r["plant"])
        if plant:
            grouped.setdefault((plant, r["standard"]), []).append(
                (r["status"], r["next_audit"])
            )
    out: dict[str, dict[str, Optional[date]]] = {}
    for (plant, standard), records in grouped.items():
        out.setdefault(plant, {})[standard] = rules.pick_next_external_audit(records, as_of)
    return out


# ─────────────────────────────────────────────────────────────
# Roles MCP: PPM (P11)
# ─────────────────────────────────────────────────────────────


def load_ppm(lookback: tuple[date, date]) -> list[rules.MetricReading]:
    """Monthly mean of the weekly PPM results vs. the latest target in the
    month, per plant."""
    start, end = lookback
    readings: list[rules.MetricReading] = []
    for kpi_id, metric in PPM_KPIS.items():
        payload = asyncio.run(
            _call_mcp_tool(
                "get_kpi_results",
                {
                    "kpi_id": kpi_id,
                    "date_from": start.isoformat(),
                    "date_to": end.isoformat(),
                    "limit": 1000,
                },
                timeout=30.0,
            )
        )
        by_plant: dict[str, list[dict]] = {}
        for row in payload.get("data") or []:
            plant = rules.normalize_plant(row.get("plant_name") or row.get("unit_name"))
            if plant and row.get("raw_value") is not None and row.get("target_value") is not None:
                by_plant.setdefault(plant, []).append(row)
        for plant, rows in by_plant.items():
            rows.sort(key=lambda r: r.get("result_date") or "")
            readings.append(
                rules.MetricReading(
                    plant=plant,
                    metric=metric,
                    value=mean(float(r["raw_value"]) for r in rows),
                    target=float(rows[-1]["target_value"]),
                    source="mcp",
                )
            )
    return readings


# ─────────────────────────────────────────────────────────────
# Manual inputs (this app's DB)
# ─────────────────────────────────────────────────────────────


def load_escalations(db: Session) -> list[rules.Escalation]:
    rows = (
        db.query(AuditPlanCustomerEscalation)
        .filter(AuditPlanCustomerEscalation.closed_on.is_(None))
        .all()
    )
    return [
        rules.Escalation(
            id=r.id,
            plant=r.plant,
            product_line=rules.normalize_product_line(r.product_line),
            customer=r.customer,
            level=r.level,
        )
        for r in rows
    ]


def load_manual_metrics(db: Session, month: date) -> list[rules.MetricReading]:
    rows = db.query(AuditPlanQualityMetric).filter(AuditPlanQualityMetric.month == month).all()
    return [
        rules.MetricReading(
            plant=r.plant,
            metric=r.metric,
            value=float(r.value),
            target=float(r.target),
            source="manual",
        )
        for r in rows
    ]


def load_history(db: Session) -> list[rules.HistoryEntry]:
    return [
        rules.HistoryEntry(
            plant=r.plant,
            product_line=rules.normalize_product_line(r.product_line),
            kind=r.kind,
            support_process_id=r.support_process_id,
            audited_on=r.audited_on,
        )
        for r in db.query(AuditPlanAuditHistory).all()
    ]


def load_support_processes(db: Session) -> list[rules.SupportProcess]:
    rows = (
        db.query(AuditPlanSupportProcess)
        .filter(AuditPlanSupportProcess.is_active.is_(True))
        .order_by(AuditPlanSupportProcess.sort_order, AuditPlanSupportProcess.id)
        .all()
    )
    return [rules.SupportProcess(id=r.id, name=r.name) for r in rows]


# ─────────────────────────────────────────────────────────────


def build_facts(db: Session, plan_month: date, as_of: date) -> rules.Facts:
    facts = rules.Facts(plan_month=plan_month, as_of=as_of)
    facts.history = load_history(db)
    facts.support_processes = load_support_processes(db)
    facts.escalations = load_escalations(db)

    def attempt(source: str, loader, *args):
        try:
            return loader(*args)
        except Exception as exc:  # noqa: BLE001 - any source failure degrades to "not evaluated"
            reason = str(exc) if isinstance(exc, SourceUnavailable) else f"{type(exc).__name__}: {exc}"
            if not isinstance(exc, SourceUnavailable):
                logger.exception("audit planning: %s source failed", source)
            facts.unavailable_reasons[source] = f"{source}: {reason}"
            return None

    lookback_start, _ = facts.lookback_month
    facts.complaints = attempt("complaints", load_complaints, as_of, lookback_start)
    facts.projects = attempt("projects", load_projects, as_of)
    facts.external_audits = attempt("certifications", load_external_audits, as_of)

    manual = load_manual_metrics(db, lookback_start)
    ppm = attempt("ppm", load_ppm, facts.lookback_month)
    if ppm is None:
        facts.unavailable_reasons["metrics_partial"] = (
            "PPM not checked - " + facts.unavailable_reasons["ppm"]
        )
    facts.metrics = manual + (ppm or [])
    return facts
