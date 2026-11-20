from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.models.user import User
from app.schemas.adminSchema.adminSchema import (
    AdminRoleCreate,
    AdminRoleResponse,
    AdminRoleUpdate,
    AdminUserCreate,
    AdminUserResponse,
    AdminUserUpdate,
    PlantHolidayCreate,
    SchedulerRunRequest,
)
from app.services.admin_service import (
    add_plant_holiday,
    create_role,
    create_user_with_roles,
    delete_role,
    delete_plant_holiday,
    delete_user,
    list_plant_holidays,
    list_roles,
    list_users,
    require_admin,
    update_role,
    update_user_with_roles,
)
from app.services.auth_service import get_current_user
from app.services.role_access_service import can_manage_plant_holidays
from app.services.car_reminder_scheduler import (
    BATCH_DELAY_SECONDS,
    MAX_EMAILS_PER_BATCH,
    MAX_RETRIES,
    RETRY_DELAY_SECONDS,
    check_and_send_reminders,
)

router = APIRouter(prefix="/admin", tags=["admin"])


def require_holiday_manager(current_user: User) -> None:
    if can_manage_plant_holidays(current_user):
        return
    raise HTTPException(
        status_code=403,
        detail="Only auditors and quality managers can access plant holidays.",
    )


@router.get("/users", response_model=list[AdminUserResponse])
def admin_list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    return list_users(db)


@router.post("/users", response_model=AdminUserResponse)
def admin_create_user(
    payload: AdminUserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    return create_user_with_roles(db, payload)


@router.put("/users/{user_id}", response_model=AdminUserResponse)
def admin_update_user(
    user_id: int,
    payload: AdminUserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    return update_user_with_roles(db, user_id, payload, acting_user_id=current_user.id)


@router.delete("/users/{user_id}")
def admin_delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    return delete_user(db, user_id, acting_user_id=current_user.id)


@router.get("/roles", response_model=list[AdminRoleResponse])
def admin_list_roles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    return list_roles(db)


@router.post("/roles", response_model=AdminRoleResponse)
def admin_create_role(
    payload: AdminRoleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    return create_role(db, payload.name)


@router.put("/roles/{role_id}", response_model=AdminRoleResponse)
def admin_update_role(
    role_id: int,
    payload: AdminRoleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    return update_role(db, role_id, payload.name)


@router.delete("/roles/{role_id}")
def admin_delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    return delete_role(db, role_id)


@router.get("/plants/holidays")
def admin_list_holidays(
    plant: Optional[str] = None,
    year: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_holiday_manager(current_user)
    return list_plant_holidays(db, plant=plant, year=year)


@router.post("/plants/holidays")
def admin_add_holiday(
    payload: PlantHolidayCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_holiday_manager(current_user)
    return add_plant_holiday(
        db=db,
        plant=payload.plant,
        holiday_date=payload.holiday_date,
        name=payload.name,
    )


@router.delete("/plants/holidays/{holiday_id}")
def admin_delete_holiday(
    holiday_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_holiday_manager(current_user)
    return delete_plant_holiday(db, holiday_id)


@router.get("/scheduler/status")
def admin_scheduler_status(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    scheduler = getattr(request.app.state, "scheduler", None)
    if not scheduler:
        return {"status": "not_initialized", "jobs": []}

    jobs = scheduler.get_jobs()
    return {
        "status": "running" if scheduler.running else "stopped",
        "jobs": [
            {
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            }
            for job in jobs
        ],
    }


@router.post("/scheduler/run")
def admin_manual_scheduler_run(
    payload: SchedulerRunRequest,
    current_user: User = Depends(get_current_user),
):
    require_admin(current_user)
    summary = check_and_send_reminders(payload.days_before)
    return {
        "message": f"Manual reminder run completed for D-{payload.days_before}.",
        "summary": summary,
    }
