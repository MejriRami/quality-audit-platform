from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from app.config.database import get_db
from app.services import role_service
from app.schemas.userSchema.roleSchema import RoleCreate, RoleUpdate, RoleResponse, RoleAssignmentRequest

router = APIRouter(prefix="/role", tags=["Roles"])


@router.post("/add")
def create_role(data: RoleCreate, db: Session = Depends(get_db)):
    return role_service.create_role(data, db)


@router.get("/all", response_model=List[RoleResponse])
def get_all_roles(db: Session = Depends(get_db)):
    return role_service.get_all_roles(db)


@router.get("/{role_id}", response_model=RoleResponse)
def get_role(role_id: int, db: Session = Depends(get_db)):
    return role_service.get_role(role_id, db)


@router.put("/{role_id}", response_model=RoleResponse)
def update_role(role_id: int, data: RoleUpdate, db: Session = Depends(get_db)):
    return role_service.update_role(role_id, data, db)


@router.delete("/{role_id}")
def delete_role(role_id: int, db: Session = Depends(get_db)):
    return role_service.delete_role(role_id, db)


@router.post("/assign-role")
def assign_role(request: RoleAssignmentRequest, db: Session = Depends(get_db)):
    return role_service.assign_role_to_user(request, db)
