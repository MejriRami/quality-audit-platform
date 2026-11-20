"""
kpi_router.py
-------------
Thin FastAPI router for all KPI endpoints.
All business / query logic lives in kpi_service.py.

URL prefix : /kpi
OpenAPI tag: kpi
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.services import kpi_service
router = APIRouter(prefix="/kpi", tags=["kpi"])


# ---------------------------------------------------------------------------
# Shared query-parameter defaults
# ---------------------------------------------------------------------------

_INTERVAL = Query("month", pattern="^(month|week)$")
_DATE_BASIS = Query("planned", pattern="^(planned|actual)$")
_DATA_SOURCE = Query("app", pattern="^(app|monday)$")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _handle(fn, *args, **kwargs) -> Any:
    """Wrap service calls and convert ValueError → 422."""
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ===========================================================================
# Time-series KPIs
# ===========================================================================


@router.get(
    "/audit-hours",
    summary="Hours of Audits by date (stacked by plant)",
)
def kpi_audit_hours(
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = None,
    plant: Optional[str] = None,
    data_source: str = _DATA_SOURCE,
    audit_type_id: Optional[int] = None,
    date_basis: str = _DATE_BASIS,
    interval: str = _INTERVAL,
    db: Session = Depends(get_db),
):
    return _handle(
        kpi_service.get_audit_hours,
        db,
        from_=from_,
        to=to,
        plant=plant,
        data_source=data_source,
        audit_type_id=audit_type_id,
        date_basis=date_basis,
        interval=interval,
    )


@router.get(
    "/audit-score-by-date",
    summary="Average Audit Score by date (all plants / all types)",
)
def kpi_audit_score_by_date(
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = None,
    plant: Optional[str] = None,
    data_source: str = _DATA_SOURCE,
    audit_type_id: Optional[int] = None,
    date_basis: str = _DATE_BASIS,
    interval: str = _INTERVAL,
    db: Session = Depends(get_db),
):
    return _handle(
        kpi_service.get_audit_score_by_date,
        db,
        from_=from_,
        to=to,
        plant=plant,
        data_source=data_source,
        audit_type_id=audit_type_id,
        date_basis=date_basis,
        interval=interval,
    )


@router.get(
    "/audit-count-score",
    summary="Number of Audits and Average Score by date (dual-axis)",
)
def kpi_audit_count_and_score(
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = None,
    plant: Optional[str] = None,
    data_source: str = _DATA_SOURCE,
    audit_type_id: Optional[int] = None,
    interval: str = _INTERVAL,
    date_basis: str = _DATE_BASIS,
    db: Session = Depends(get_db),
):
    return _handle(
        kpi_service.get_audit_count_and_score,
        db,
        from_=from_,
        to=to,
        plant=plant,
        data_source=data_source,
        audit_type_id=audit_type_id,
        interval=interval,
        date_basis=date_basis,
    )


@router.get(
    "/car-count",
    summary="Number of CARs by date (stacked by plant)",
)
def kpi_car_count(
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = None,
    plant: Optional[str] = None,
    data_source: str = _DATA_SOURCE,
    interval: str = _INTERVAL,
    db: Session = Depends(get_db),
):
    return _handle(
        kpi_service.get_car_count,
        db,
        from_=from_,
        to=to,
        plant=plant,
        data_source=data_source,
        interval=interval,
    )


@router.get(
    "/late-car",
    summary="Late CARs by period (stacked by plant)",
)
def kpi_late_car(
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = None,
    plant: Optional[str] = None,
    data_source: str = _DATA_SOURCE,
    interval: str = Query("week", pattern="^(week|month)$"),
    db: Session = Depends(get_db),
):
    return _handle(
        kpi_service.get_late_car,
        db,
        from_=from_,
        to=to,
        plant=plant,
        data_source=data_source,
        interval=interval,
    )


@router.get(
    "/avg-days-close-car",
    summary="Average calendar days to close a CAR by date",
)
def kpi_avg_days_close_car(
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = None,
    plant: Optional[str] = None,
    data_source: str = _DATA_SOURCE,
    interval: str = _INTERVAL,
    db: Session = Depends(get_db),
):
    return _handle(
        kpi_service.get_avg_days_close_car,
        db,
        from_=from_,
        to=to,
        plant=plant,
        data_source=data_source,
        interval=interval,
    )


# ===========================================================================
# Category KPIs  (grouped by plant / audit)
# ===========================================================================


@router.get(
    "/audits-by-type-plant",
    summary="Audit count per type per plant (stacked bar)",
)
def kpi_audits_by_type_and_plant(
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = None,
    plant: Optional[str] = None,
    data_source: str = _DATA_SOURCE,
    audit_type_id: Optional[int] = None,
    date_basis: str = _DATE_BASIS,
    db: Session = Depends(get_db),
):
    return _handle(
        kpi_service.get_audits_by_type_and_plant,
        db,
        from_=from_,
        to=to,
        plant=plant,
        data_source=data_source,
        audit_type_id=audit_type_id,
        date_basis=date_basis,
    )


@router.get(
    "/working-days-close-car-by-plant",
    summary="Average working days to close CARs, by plant",
)
def kpi_working_days_close_car_by_plant(
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = None,
    plant: Optional[str] = None,
    data_source: str = _DATA_SOURCE,
    db: Session = Depends(get_db),
):
    return _handle(
        kpi_service.get_working_days_close_car_by_plant,
        db,
        from_=from_,
        to=to,
        plant=plant,
        data_source=data_source,
    )


@router.get(
    "/open-car-by-plant",
    summary="Number of open CARs by plant",
)
def kpi_open_car_by_plant(
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = None,
    plant: Optional[str] = None,
    data_source: str = _DATA_SOURCE,
    db: Session = Depends(get_db),
):
    return _handle(
        kpi_service.get_open_car_by_plant,
        db,
        from_=from_,
        to=to,
        plant=plant,
        data_source=data_source,
    )


@router.get(
    "/late-open-car-by-plant",
    summary="Number of late open CARs by plant",
)
def kpi_late_open_car_by_plant(
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = None,
    plant: Optional[str] = None,
    data_source: str = _DATA_SOURCE,
    db: Session = Depends(get_db),
):
    return _handle(
        kpi_service.get_late_open_car_by_plant,
        db,
        from_=from_,
        to=to,
        plant=plant,
        data_source=data_source,
    )


@router.get(
    "/closed-late-car-by-plant",
    summary="Number of closed-but-late CARs by plant",
)
def kpi_closed_late_car_by_plant(
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = None,
    plant: Optional[str] = None,
    data_source: str = _DATA_SOURCE,
    db: Session = Depends(get_db),
):
    return _handle(
        kpi_service.get_closed_late_car_by_plant,
        db,
        from_=from_,
        to=to,
        plant=plant,
        data_source=data_source,
    )


@router.get(
    "/avg-audit-score-by-plant",
    summary="Average Audit Score by plant",
)
def kpi_avg_audit_score_by_plant(
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = None,
    plant: Optional[str] = None,
    data_source: str = _DATA_SOURCE,
    audit_type_id: Optional[int] = None,
    date_basis: str = _DATE_BASIS,
    db: Session = Depends(get_db),
):
    return _handle(
        kpi_service.get_avg_audit_score_by_plant,
        db,
        from_=from_,
        to=to,
        plant=plant,
        data_source=data_source,
        audit_type_id=audit_type_id,
        date_basis=date_basis,
    )


@router.get(
    "/audit-status-by-period",
    summary="Audit status breakdown by period (stacked)",
)
def kpi_audit_status_by_period(
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = None,
    plant: Optional[str] = None,
    data_source: str = _DATA_SOURCE,
    audit_type_id: Optional[int] = None,
    interval: str = _INTERVAL,
    date_basis: str = _DATE_BASIS,
    db: Session = Depends(get_db),
):
    return _handle(
        kpi_service.get_audit_status_by_period,
        db,
        from_=from_,
        to=to,
        plant=plant,
        data_source=data_source,
        audit_type_id=audit_type_id,
        interval=interval,
        date_basis=date_basis,
    )


@router.get(
    "/audit-status-by-plant",
    summary="Audit status breakdown by plant (stacked)",
)
def kpi_audit_status_by_plant(
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = None,
    plant: Optional[str] = None,
    data_source: str = _DATA_SOURCE,
    audit_type_id: Optional[int] = None,
    date_basis: str = _DATE_BASIS,
    db: Session = Depends(get_db),
):
    return _handle(
        kpi_service.get_audit_status_by_plant,
        db,
        from_=from_,
        to=to,
        plant=plant,
        data_source=data_source,
        audit_type_id=audit_type_id,
        date_basis=date_basis,
    )


@router.get(
    "/open-car-by-audit",
    summary="Top-N audits by number of open CARs",
)
def kpi_open_car_by_audit(
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = None,
    plant: Optional[str] = None,
    data_source: str = _DATA_SOURCE,
    limit: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return _handle(
        kpi_service.get_open_car_by_audit,
        db,
        from_=from_,
        to=to,
        limit=limit,
        plant=plant,
        data_source=data_source,
    )


@router.get(
    "/plant-audit-car-overview",
    summary="Plant overview: total/closed CARs, audits and avg score",
)
def kpi_plant_audit_car_overview(
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = None,
    plant: Optional[str] = None,
    data_source: str = _DATA_SOURCE,
    audit_type_id: Optional[int] = None,
    date_basis: str = _DATE_BASIS,
    db: Session = Depends(get_db),
):
    return _handle(
        kpi_service.get_plant_audit_car_overview,
        db,
        from_=from_,
        to=to,
        plant=plant,
        data_source=data_source,
        audit_type_id=audit_type_id,
        date_basis=date_basis,
    )


@router.get(
    "/avg-score-by-focus-type",
    summary="Average score by focus type (VDA / PM-IATF / ISO-IATF / usage of glasses)",
)
def kpi_avg_score_by_focus_type(
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = None,
    plant: Optional[str] = None,
    data_source: str = _DATA_SOURCE,
    audit_type_id: Optional[int] = None,
    date_basis: str = _DATE_BASIS,
    db: Session = Depends(get_db),
):
    return _handle(
        kpi_service.get_avg_score_by_focus_type,
        db,
        from_=from_,
        to=to,
        plant=plant,
        data_source=data_source,
        audit_type_id=audit_type_id,
        date_basis=date_basis,
    )


@router.get(
    "/avg-score-by-type-plant",
    summary="Average score by audit type and plant",
)
def kpi_avg_score_by_type_and_plant(
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = None,
    plant: Optional[str] = None,
    data_source: str = _DATA_SOURCE,
    audit_type_id: Optional[int] = None,
    date_basis: str = _DATE_BASIS,
    db: Session = Depends(get_db),
):
    return _handle(
        kpi_service.get_avg_score_by_type_and_plant,
        db,
        from_=from_,
        to=to,
        plant=plant,
        data_source=data_source,
        audit_type_id=audit_type_id,
        date_basis=date_basis,
    )


@router.get(
    "/planned-vs-execution",
    summary="Planned audits vs execution/report creation (created_at)",
)
def kpi_planned_vs_execution(
    from_: Optional[date] = Query(None, alias="from"),
    to: Optional[date] = None,
    plant: Optional[str] = None,
    data_source: str = _DATA_SOURCE,
    audit_type_id: Optional[int] = None,
    interval: str = _INTERVAL,
    date_basis: str = _DATE_BASIS,
    db: Session = Depends(get_db),
):
    return _handle(
        kpi_service.get_planned_vs_execution,
        db,
        from_=from_,
        to=to,
        plant=plant,
        data_source=data_source,
        audit_type_id=audit_type_id,
        interval=interval,
        date_basis=date_basis,
    )
