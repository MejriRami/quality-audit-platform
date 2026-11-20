from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session,joinedload
from typing import List
from app.config.database import get_db
from app.models.user import User
from app.schemas.schema import FrameworkCreate, FrameworkUpdate
from app.services.auth_service import get_current_user
from app.services import framework_service
from app.services.role_access_service import can_manage_frameworks

router = APIRouter(
    prefix="/framework",
    tags=["frameworks"],
    dependencies=[Depends(get_current_user)],
)


def require_framework_manager(current_user: User) -> None:
    if can_manage_frameworks(current_user):
        return
    raise HTTPException(
        status_code=403,
        detail="Only auditors, quality managers, and admins can manage frameworks.",
    )


@router.post("/add")
def create_framework(
    data: FrameworkCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_framework_manager(current_user)
    return framework_service.create_framework(data, db)

@router.put("/{id}")
def update_framework(
    id: int,
    data: FrameworkUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_framework_manager(current_user)
    return framework_service.update_framework(id, data, db)

@router.get("/getAll")
def get_frameworks(db: Session = Depends(get_db)):
    return framework_service.get_all_frameworks(db)
    
@router.get("/{id}")
def get_framework(id: int, db: Session = Depends(get_db)):
    return framework_service.get_framework(id, db)


@router.delete("/{id}")
def delete_framework(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_framework_manager(current_user)
    return framework_service.delete_framework(id, db)

