from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole
from app.schemas.userSchema.roleSchema import RoleCreate, RoleUpdate, RoleAssignmentRequest


def create_role(data: RoleCreate, db: Session):
    existing = db.query(Role).filter_by(name=data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Role name already registered")
    role = Role(name=data.name)
    db.add(role)
    db.commit()
    db.refresh(role)
    return role


def get_all_roles(db: Session):
    return db.query(Role).all()


def get_role(role_id: int, db: Session):
    role = db.query(Role).filter_by(id=role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return role


def update_role(role_id: int, data: RoleUpdate, db: Session):
    role = db.query(Role).filter_by(id=role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    role.name = data.name
    db.commit()
    db.refresh(role)
    return role


def delete_role(role_id: int, db: Session):
    role = db.query(Role).filter_by(id=role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    db.delete(role)
    db.commit()
    return {"message": f"Role has been deleted successfully"}


def assign_role_to_user(request: RoleAssignmentRequest, db: Session):
    user = db.query(User).filter_by(email=request.user_email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    role = db.query(Role).filter_by(name=request.role_name).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    existing = db.query(UserRole).filter_by(user_id=user.id, role_id=role.id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Role already assigned to user")

    assignment = UserRole(user_id=user.id, role_id=role.id)
    db.add(assignment)
    db.commit()
    return {"message": f"Role '{role.name}' assigned to user '{user.email}'"}