from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.services import user_service  
from typing import Annotated, List
from app.schemas.userSchema.userSchema import UserCreate, UserResponse, UserUpdate, UserUpdatePassword, UserUpdatePasswordResponse
from fastapi.security import OAuth2PasswordRequestForm


router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/add", response_model=UserResponse)
def create_user(data: UserCreate, db: Session = Depends(get_db)):
    return user_service.create_user(data, db)

@router.get("/all", response_model=List[UserResponse])
def get_all_users(db: Session = Depends(get_db)):
    return user_service.get_all_users(db)

@router.get("/auditors")
def get_auditors(db: Session = Depends(get_db)):
    return user_service.get_auditors(db)

@router.get("/{user_id}", response_model=UserResponse)
def get_user_by_id(user_id: int, db: Session = Depends(get_db)):
    return user_service.get_user_by_id(user_id, db)

@router.put("/{user_id}", response_model=UserResponse)
def update_user(user_id: int, data: UserUpdate, db: Session = Depends(get_db)):
    return user_service.update_user(user_id, data, db)

@router.delete("/{user_id}", response_model=dict)
def delete_user(user_id: int, db: Session = Depends(get_db)):
    return user_service.delete_user(user_id, db)