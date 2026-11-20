from typing_extensions import Annotated
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from app.config.database import get_db
from app.schemas.authSchema.authSchema import LoginSchema
from app.schemas.userSchema.userSchema import UserResponse, UserUpdatePassword, UserUpdatePasswordResponse
from app.services import auth_service
from sqlalchemy.orm import Session
import traceback

router = APIRouter(prefix="", tags=["authentication"])

@router.post("/login")
def login(data: LoginSchema, db: Session = Depends(get_db)):
    try:
        return auth_service.login(data, db)
    except HTTPException:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        return JSONResponse(
            status_code=500,
            content={
                "error": type(e).__name__,
                "message": str(e),
                "traceback": tb,
            }
        )

@router.post('/reset-password', response_model=UserUpdatePasswordResponse)
def reset_password(data: UserUpdatePassword, db: Session = Depends(get_db)):
    return auth_service.reset_password(data, db)

@router.get('/me', response_model=UserResponse)
def get_current_user_route(
    current_user=Depends(auth_service.get_current_user)
):
    return current_user
