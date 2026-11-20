from __future__ import annotations

from datetime import date
from typing import Iterable, Optional

from fastapi import HTTPException
from sqlalchemy import and_, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.plant_holiday import PlantHoliday
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole
from app.schemas.adminSchema.adminSchema import AdminUserCreate, AdminUserUpdate
from app.services.auth_service import bcrypt_context
from app.services.role_access_service import has_admin_role
from app.utils.due_date import EXTRA_HOLIDAYS_BY_PLANT, PLANT_COUNTRY


ADMIN_ROLE_NAMES = {"admin"}
PROTECTED_ROLE_NAMES = set(ADMIN_ROLE_NAMES)
DEFAULT_ROLE_NAMES = ("quality_manager", "editor", "certification_editor", "certification_viewer")


def _is_admin_role_name(role_name: str) -> bool:
    normalized = (role_name or "").strip().lower()
    return normalized in ADMIN_ROLE_NAMES


def _extract_user_role_names(user: User) -> set[str]:
    return {
        (getattr(getattr(ur, "role", None), "name", "") or "").strip().lower()
        for ur in (user.roles or [])
        if getattr(getattr(ur, "role", None), "name", None)
    }


def _count_active_admin_users(db: Session) -> int:
    return (
        db.query(User.id)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .filter(User.active.is_(True), func.lower(Role.name).in_(list(ADMIN_ROLE_NAMES)))
        .distinct()
        .count()
    )


def require_admin(user: User) -> None:
    if has_admin_role(user):
        return
    raise HTTPException(status_code=403, detail="Admin access required.")


def _normalize_role_names(values: Optional[Iterable[str]]) -> list[str]:
    if not values:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for role_name in values:
        normalized = (role_name or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        out.append(normalized)
        seen.add(normalized)
    return out


def _to_user_dict(user: User) -> dict:
    role_names = sorted(
        {
            (getattr(getattr(ur, "role", None), "name", "") or "").strip().lower()
            for ur in (user.roles or [])
            if getattr(getattr(ur, "role", None), "name", None)
        }
    )
    return {
        "id": user.id,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "active": bool(user.active),
        "role_names": role_names,
    }


def list_users(db: Session) -> list[dict]:
    users = (
        db.query(User)
        .options(joinedload(User.roles).joinedload(UserRole.role))
        .order_by(User.id.asc())
        .all()
    )
    return [_to_user_dict(u) for u in users]


def _resolve_roles(db: Session, role_names: list[str]) -> list[Role]:
    roles: list[Role] = []
    for role_name in role_names:
        role = db.query(Role).filter(func.lower(Role.name) == role_name).first()
        if role is None:
            raise HTTPException(
                status_code=400,
                detail=f"Role '{role_name}' does not exist. Create it first in Role Management.",
            )
        roles.append(role)
    return roles


def create_user_with_roles(db: Session, data: AdminUserCreate) -> dict:
    existing = db.query(User).filter(func.lower(User.email) == str(data.email).lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered.")

    user = User(
        first_name=data.first_name.strip(),
        last_name=data.last_name.strip(),
        email=str(data.email).strip().lower(),
        password=bcrypt_context.hash(data.password),
        active=bool(data.active),
    )
    db.add(user)
    db.flush()

    role_names = _normalize_role_names(data.role_names)
    roles = _resolve_roles(db, role_names)
    for role in roles:
        db.add(UserRole(user_id=user.id, role_id=role.id))

    db.commit()
    db.refresh(user)
    user = (
        db.query(User)
        .options(joinedload(User.roles).joinedload(UserRole.role))
        .filter(User.id == user.id)
        .first()
    )
    return _to_user_dict(user)


def update_user_with_roles(db: Session, user_id: int, data: AdminUserUpdate, acting_user_id: int) -> dict:
    user = (
        db.query(User)
        .options(joinedload(User.roles).joinedload(UserRole.role))
        .filter(User.id == user_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    current_roles = _extract_user_role_names(user)
    is_current_admin = any(_is_admin_role_name(r) for r in current_roles)
    will_be_active = bool(user.active) if data.active is None else bool(data.active)
    desired_role_names = current_roles
    if data.role_names is not None:
        desired_role_names = set(_normalize_role_names(data.role_names))
    will_be_admin = any(_is_admin_role_name(r) for r in desired_role_names)

    if is_current_admin and (not will_be_active or not will_be_admin):
        if _count_active_admin_users(db) <= 1:
            raise HTTPException(
                status_code=400,
                detail="At least one active admin user is required.",
            )

    if data.email is not None:
        new_email = str(data.email).strip().lower()
        existing = db.query(User).filter(and_(func.lower(User.email) == new_email, User.id != user_id)).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already used by another user.")
        user.email = new_email

    if data.first_name is not None:
        user.first_name = data.first_name.strip()
    if data.last_name is not None:
        user.last_name = data.last_name.strip()
    if data.active is not None:
        user.active = bool(data.active)
    if data.password:
        user.password = bcrypt_context.hash(data.password)

    if data.role_names is not None:
        desired = _normalize_role_names(data.role_names)
        roles = _resolve_roles(db, desired)
        db.query(UserRole).filter(UserRole.user_id == user.id).delete()
        for role in roles:
            db.add(UserRole(user_id=user.id, role_id=role.id))

    if user.id == acting_user_id and user.active is False:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account.")

    db.commit()
    db.refresh(user)
    user = (
        db.query(User)
        .options(joinedload(User.roles).joinedload(UserRole.role))
        .filter(User.id == user.id)
        .first()
    )
    return _to_user_dict(user)


def delete_user(db: Session, user_id: int, acting_user_id: int) -> dict:
    if user_id == acting_user_id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account.")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    user_with_roles = (
        db.query(User)
        .options(joinedload(User.roles).joinedload(UserRole.role))
        .filter(User.id == user_id)
        .first()
    )
    if user_with_roles and user_with_roles.active:
        role_names = _extract_user_role_names(user_with_roles)
        if any(_is_admin_role_name(r) for r in role_names):
            if _count_active_admin_users(db) <= 1:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot remove the last active admin user.",
                )

    try:
        db.delete(user)
        db.commit()
    except IntegrityError:
        db.rollback()
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        user.active = False
        db.commit()
        return {
            "message": "User had linked records and was deactivated instead of deleted."
        }
    return {"message": "User deleted successfully."}


def list_roles(db: Session) -> list[dict]:
    roles = db.query(Role).order_by(Role.name.asc()).all()
    return [{"id": role.id, "name": role.name} for role in roles]


def ensure_default_roles(db: Session, role_names: Iterable[str] = DEFAULT_ROLE_NAMES) -> list[str]:
    created: list[str] = []
    for role_name in _normalize_role_names(role_names):
        existing = db.query(Role).filter(func.lower(Role.name) == role_name).first()
        if existing is not None:
            continue
        db.add(Role(name=role_name))
        created.append(role_name)

    if created:
        db.commit()

    return created


def create_role(db: Session, name: str) -> dict:
    normalized = (name or "").strip().lower()
    if len(normalized) < 2:
        raise HTTPException(status_code=400, detail="Role name is too short.")

    existing = db.query(Role).filter(func.lower(Role.name) == normalized).first()
    if existing:
        raise HTTPException(status_code=400, detail="Role already exists.")

    role = Role(name=normalized)
    db.add(role)
    db.commit()
    db.refresh(role)
    return {"id": role.id, "name": role.name}


def update_role(db: Session, role_id: int, name: str) -> dict:
    normalized = (name or "").strip().lower()
    if len(normalized) < 2:
        raise HTTPException(status_code=400, detail="Role name is too short.")

    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found.")
    current_name = (role.name or "").strip().lower()
    if current_name in PROTECTED_ROLE_NAMES and normalized != current_name:
        raise HTTPException(
            status_code=400,
            detail=f"Role '{current_name}' is protected and cannot be renamed.",
        )

    existing = (
        db.query(Role)
        .filter(func.lower(Role.name) == normalized, Role.id != role_id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Role name already exists.")

    role.name = normalized
    db.commit()
    db.refresh(role)
    return {"id": role.id, "name": role.name}


def delete_role(db: Session, role_id: int) -> dict:
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found.")

    normalized_role_name = (role.name or "").strip().lower()
    if normalized_role_name in PROTECTED_ROLE_NAMES:
        raise HTTPException(
            status_code=400,
            detail=f"Role '{normalized_role_name}' is protected and cannot be deleted.",
        )

    detached_count = db.query(UserRole).filter(UserRole.role_id == role.id).delete()
    db.delete(role)
    db.commit()
    return {
        "message": "Role deleted successfully.",
        "detached_users_count": detached_count,
    }


def list_plant_holidays(
    db: Session,
    *,
    plant: Optional[str] = None,
    year: Optional[int] = None,
) -> dict:
    query = db.query(PlantHoliday)
    if plant:
        query = query.filter(func.lower(PlantHoliday.plant) == plant.strip().lower())
    if year:
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        query = query.filter(
            PlantHoliday.holiday_date >= start_date,
            PlantHoliday.holiday_date <= end_date,
        )
    rows = query.order_by(PlantHoliday.holiday_date.asc(), PlantHoliday.id.asc()).all()
    return {
        "system_plants": sorted(PLANT_COUNTRY.keys()),
        "code_based_extras": {
            p: sorted(d.isoformat() for d in dates)
            for p, dates in EXTRA_HOLIDAYS_BY_PLANT.items()
        },
        "items": [
            {
                "id": row.id,
                "plant": row.plant,
                "holiday_date": row.holiday_date.isoformat(),
                "name": row.name,
            }
            for row in rows
        ],
    }


def add_plant_holiday(db: Session, plant: str, holiday_date: date, name: Optional[str]) -> dict:
    plant_key = (plant or "").strip().lower()
    if plant_key not in PLANT_COUNTRY:
        known = ", ".join(sorted(PLANT_COUNTRY.keys()))
        raise HTTPException(status_code=400, detail=f"Unknown plant '{plant}'. Known: {known}")

    existing = (
        db.query(PlantHoliday)
        .filter(
            func.lower(PlantHoliday.plant) == plant_key,
            PlantHoliday.holiday_date == holiday_date,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Holiday already exists for this plant/date.")

    row = PlantHoliday(plant=plant_key, holiday_date=holiday_date, name=(name or "").strip() or None)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "plant": row.plant,
        "holiday_date": row.holiday_date.isoformat(),
        "name": row.name,
    }


def delete_plant_holiday(db: Session, holiday_id: int) -> dict:
    row = db.query(PlantHoliday).filter(PlantHoliday.id == holiday_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Holiday entry not found.")
    db.delete(row)
    db.commit()
    return {"message": "Holiday deleted successfully."}
