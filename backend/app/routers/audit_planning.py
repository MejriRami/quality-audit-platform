"""Monthly audit plan: generate, review/override, approve, complete - plus the
manual inputs the engine reads (CSI/CSII, NQC/scrap, audit history, support
processes). Admin / quality-manager only."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import AfterValidator, BaseModel, Field, field_validator
from sqlalchemy.orm import Session, selectinload

from app.config.database import get_db
from app.models.audit_planning import (
    AuditPlanAuditHistory,
    AuditPlanCustomerEscalation,
    AuditPlanItem,
    AuditPlanQualityMetric,
    AuditPlanRun,
    AuditPlanSupportProcess,
)
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole
from app.services.audit_planning import rules, service
from app.services.auth_service import get_current_user
from app.services.role_access_service import AUDITOR_ROLE_NAME, is_admin_or_quality_manager

router = APIRouter(prefix="/audit-planning", tags=["Audit Planning"])


def planner(current_user: User = Depends(get_current_user)) -> User:
    if not is_admin_or_quality_manager(current_user):
        raise HTTPException(status_code=403, detail="Admin or quality manager access required.")
    return current_user


def _run_service(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except service.PlanError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


def _plant(value: str) -> str:
    plant = rules.normalize_plant(value)
    if plant not in rules.SCHEDULED_PLANTS:
        raise ValueError(f"Unknown plant '{value}'. Expected one of: {', '.join(rules.SCHEDULED_PLANTS)}")
    return plant


Plant = Annotated[str, AfterValidator(_plant)]


# ─────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────


class ItemOut(BaseModel):
    id: int
    plant: str
    product_line: Optional[str]
    project_code: Optional[str]
    support_process_id: Optional[int]
    trigger_codes: list[str]
    checklist: str
    evidence: list[dict]
    complaint_volume: int
    priority: int
    status: str
    status_reason: Optional[str]
    scheduled_date: Optional[date]
    auditor_user_id: Optional[int]
    auditee_role: str
    auditee_name: Optional[str]
    auditee_email: Optional[str]
    auditee_status: str
    auditee_note: Optional[str]
    overridden: bool
    override_note: Optional[str]
    completed_on: Optional[date]

    class Config:
        from_attributes = True


class RunSummaryOut(BaseModel):
    id: int
    plan_month: date
    status: str
    as_of: date
    generated_at: datetime
    approved_at: Optional[datetime]

    class Config:
        from_attributes = True


class RunOut(RunSummaryOut):
    check_status: dict
    warnings: list[str]
    items: list[ItemOut]


class GenerateIn(BaseModel):
    plan_month: date


class ItemPatch(BaseModel):
    status: Optional[str] = None
    scheduled_date: Optional[date] = None
    auditor_user_id: Optional[int] = None
    auditee_name: Optional[str] = None
    auditee_email: Optional[str] = None
    override_note: Optional[str] = None


class CompleteIn(BaseModel):
    completed_on: date


class AuditorOut(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str

    class Config:
        from_attributes = True


class EscalationIn(BaseModel):
    plant: Plant
    product_line: Optional[str] = None
    customer: Optional[str] = None
    level: Literal["CSI", "CSII"]
    opened_on: date
    closed_on: Optional[date] = None
    reference: Optional[str] = None
    note: Optional[str] = None


class EscalationOut(EscalationIn):
    id: int

    class Config:
        from_attributes = True


class MetricIn(BaseModel):
    plant: Plant
    month: date
    metric: Literal["nqc", "scrap"]
    value: Decimal
    target: Decimal
    unit: Optional[str] = None
    note: Optional[str] = None

    @field_validator("month")
    @classmethod
    def _first_of_month(cls, v: date) -> date:
        return v.replace(day=1)


class MetricOut(MetricIn):
    id: int

    class Config:
        from_attributes = True


class HistoryIn(BaseModel):
    plant: Plant
    product_line: Optional[str] = None
    kind: Literal[rules.HISTORY_KINDS]  # type: ignore[valid-type]
    support_process_id: Optional[int] = None
    audited_on: date
    note: Optional[str] = None


class HistoryOut(HistoryIn):
    id: int
    source: str
    plan_item_id: Optional[int]

    class Config:
        from_attributes = True


class SupportProcessIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    is_active: bool = True
    sort_order: int = 0


class SupportProcessOut(SupportProcessIn):
    id: int

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────────────────────
# Plan runs
# ─────────────────────────────────────────────────────────────


@router.get("/meta")
def get_meta(user: User = Depends(planner)):
    return {
        "plants": list(rules.SCHEDULED_PLANTS),
        "schedule": {
            group: {"weekday": weekday, "plants": list(plants)}
            for group, (weekday, plants) in rules.SCHEDULE_GROUPS.items()
        },
        "history_kinds": list(rules.HISTORY_KINDS),
        "editable_statuses": sorted(service.EDITABLE_STATUSES),
        "priorities": [
            {"code": code, "auditee_role": rules.AUDITEE_ROLE[code], **guide}
            for code, guide in rules.PRIORITY_GUIDE.items()
        ],
    }


@router.get("/runs", response_model=list[RunSummaryOut])
def list_runs(db: Session = Depends(get_db), user: User = Depends(planner)):
    return db.query(AuditPlanRun).order_by(AuditPlanRun.plan_month.desc(), AuditPlanRun.id.desc()).limit(36).all()


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: int, db: Session = Depends(get_db), user: User = Depends(planner)):
    run = (
        db.query(AuditPlanRun)
        .options(selectinload(AuditPlanRun.items))
        .filter(AuditPlanRun.id == run_id)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Plan run not found.")
    return run


@router.post("/runs", response_model=RunOut)
def generate_run(body: GenerateIn, db: Session = Depends(get_db), user: User = Depends(planner)):
    """Evaluate P1-P11 now and store a fresh draft for the month (supersedes
    any earlier draft for that month)."""
    return _run_service(service.generate_plan, db, body.plan_month, user_id=user.id)


@router.post("/runs/{run_id}/approve", response_model=RunSummaryOut)
def approve_run(run_id: int, db: Session = Depends(get_db), user: User = Depends(planner)):
    return _run_service(service.approve_run, db, run_id, user)


@router.patch("/items/{item_id}", response_model=ItemOut)
def patch_item(item_id: int, body: ItemPatch, db: Session = Depends(get_db), user: User = Depends(planner)):
    return _run_service(service.update_item, db, item_id, body.model_dump(exclude_unset=True), user)


@router.post("/items/{item_id}/complete", response_model=ItemOut)
def complete_item(item_id: int, body: CompleteIn, db: Session = Depends(get_db), user: User = Depends(planner)):
    return _run_service(service.complete_item, db, item_id, body.completed_on, user)


@router.get("/auditors", response_model=list[AuditorOut])
def list_auditors(db: Session = Depends(get_db), user: User = Depends(planner)):
    return (
        db.query(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .filter(User.active.is_(True), Role.name.ilike(AUDITOR_ROLE_NAME))
        .order_by(User.first_name, User.last_name)
        .all()
    )


# ─────────────────────────────────────────────────────────────
# Manual inputs
# ─────────────────────────────────────────────────────────────


def _get_or_404(db: Session, model, row_id: int):
    row = db.get(model, row_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found.")
    return row


def _save(db: Session, row, data: dict, user: Optional[User] = None, user_field: Optional[str] = None):
    for key, value in data.items():
        setattr(row, key, value)
    if user_field:
        setattr(row, user_field, user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/escalations", response_model=list[EscalationOut])
def list_escalations(open_only: bool = False, db: Session = Depends(get_db), user: User = Depends(planner)):
    q = db.query(AuditPlanCustomerEscalation)
    if open_only:
        q = q.filter(AuditPlanCustomerEscalation.closed_on.is_(None))
    return q.order_by(AuditPlanCustomerEscalation.opened_on.desc()).all()


@router.post("/escalations", response_model=EscalationOut)
def create_escalation(body: EscalationIn, db: Session = Depends(get_db), user: User = Depends(planner)):
    return _save(db, AuditPlanCustomerEscalation(), body.model_dump(), user, "updated_by_user_id")


@router.put("/escalations/{row_id}", response_model=EscalationOut)
def update_escalation(row_id: int, body: EscalationIn, db: Session = Depends(get_db), user: User = Depends(planner)):
    row = _get_or_404(db, AuditPlanCustomerEscalation, row_id)
    return _save(db, row, body.model_dump(), user, "updated_by_user_id")


@router.delete("/escalations/{row_id}", status_code=204)
def delete_escalation(row_id: int, db: Session = Depends(get_db), user: User = Depends(planner)):
    db.delete(_get_or_404(db, AuditPlanCustomerEscalation, row_id))
    db.commit()


@router.get("/metrics", response_model=list[MetricOut])
def list_metrics(db: Session = Depends(get_db), user: User = Depends(planner)):
    return db.query(AuditPlanQualityMetric).order_by(
        AuditPlanQualityMetric.month.desc(), AuditPlanQualityMetric.plant
    ).limit(500).all()


@router.post("/metrics", response_model=MetricOut)
def upsert_metric(body: MetricIn, db: Session = Depends(get_db), user: User = Depends(planner)):
    """One value per plant/month/metric - posting again replaces it."""
    row = (
        db.query(AuditPlanQualityMetric)
        .filter_by(plant=body.plant, month=body.month, metric=body.metric)
        .first()
    ) or AuditPlanQualityMetric()
    return _save(db, row, body.model_dump(), user, "updated_by_user_id")


@router.delete("/metrics/{row_id}", status_code=204)
def delete_metric(row_id: int, db: Session = Depends(get_db), user: User = Depends(planner)):
    db.delete(_get_or_404(db, AuditPlanQualityMetric, row_id))
    db.commit()


@router.get("/history", response_model=list[HistoryOut])
def list_history(db: Session = Depends(get_db), user: User = Depends(planner)):
    return db.query(AuditPlanAuditHistory).order_by(AuditPlanAuditHistory.audited_on.desc()).limit(500).all()


@router.post("/history", response_model=HistoryOut)
def create_history(body: HistoryIn, db: Session = Depends(get_db), user: User = Depends(planner)):
    if body.kind == rules.HISTORY_SUPPORT_PROCESS and not body.support_process_id:
        raise HTTPException(status_code=422, detail="Support-process history needs support_process_id.")
    return _save(db, AuditPlanAuditHistory(source="manual"), body.model_dump(), user, "created_by_user_id")


@router.delete("/history/{row_id}", status_code=204)
def delete_history(row_id: int, db: Session = Depends(get_db), user: User = Depends(planner)):
    row = _get_or_404(db, AuditPlanAuditHistory, row_id)
    if row.source != "manual":
        raise HTTPException(status_code=409, detail="History written by a completed plan item can't be deleted here.")
    db.delete(row)
    db.commit()


@router.get("/support-processes", response_model=list[SupportProcessOut])
def list_support_processes(db: Session = Depends(get_db), user: User = Depends(planner)):
    return db.query(AuditPlanSupportProcess).order_by(
        AuditPlanSupportProcess.sort_order, AuditPlanSupportProcess.id
    ).all()


@router.post("/support-processes", response_model=SupportProcessOut)
def create_support_process(body: SupportProcessIn, db: Session = Depends(get_db), user: User = Depends(planner)):
    return _save(db, AuditPlanSupportProcess(), body.model_dump())


@router.put("/support-processes/{row_id}", response_model=SupportProcessOut)
def update_support_process(
    row_id: int, body: SupportProcessIn, db: Session = Depends(get_db), user: User = Depends(planner)
):
    return _save(db, _get_or_404(db, AuditPlanSupportProcess, row_id), body.model_dump())
