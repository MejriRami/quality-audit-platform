from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole
from app.schemas.userSchema.userSchema import UserCreate, UserUpdate
from .auth_service import bcrypt_context


def create_user(data: UserCreate, db: Session):
    db_user = db.query(User).filter(User.email == data.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(
        first_name=data.first_name,
        last_name=data.last_name,
        password = bcrypt_context.hash(data.password),
        email=data.email,
        active=True
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


def get_all_users(db: Session):
    users= db.query(User).all()
    if users is None:
        raise HTTPException(status_code=404, detail="Empty list")
    return users

def get_auditors(db: Session):
    auditors = (
        db.query(User)
        .join(UserRole, User.id == UserRole.user_id)
        .join(Role, Role.id == UserRole.role_id)
        .filter(Role.name == "auditor")
        # .options(joinedload(User.roles))  # optional, if you want to include roles
        .all()
    )

    if not auditors:  # empty list check
        raise HTTPException(status_code=404, detail="No auditors found")

    # return auditors
    return [{"id": u.id, "fullName": u.first_name+" "+u.last_name, "email": u.email} for u in auditors]


def get_user_by_email(user_email: str, db: Session):
    user = db.query(User).filter(User.email == user_email).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def get_user_by_id(user_id: int, db: Session):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def update_user(user_id: int, data: UserUpdate, db: Session):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    user.last_name = data.last_name if data.last_name is not None else user.last_name
    user.first_name = data.first_name if data.first_name is not None else user.first_name
    user.email = data.email if data.email is not None else user.email
    if data.password is not None:
        user.password = bcrypt_context.hash(data.password)
    user.active = data.active if data.active is not None else user.active

    db.commit()
    db.refresh(user)
    return user


def delete_user(user_id: int, db: Session):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="this user does not already exist")

    db.delete(user)
    db.commit()
    return {"message": f"User has been deleted successfully"}
