
import os
import logging
from typing import Annotated, Optional
import bcrypt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
import jwt
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from passlib.exc import MissingBackendError, UnknownHashError
from fastapi.security import OAuth2PasswordBearer
from app.config.database import get_db
from app.models.user import User
from datetime import datetime, timedelta

from app.schemas.userSchema.userSchema import UserUpdatePassword

load_dotenv()

bcrypt_context = CryptContext(schemes=["argon2"], deprecated="auto")
oauth2_bearer = OAuth2PasswordBearer(tokenUrl="auth/token")
logger = logging.getLogger(__name__)

db_dependency = Annotated[Session, Depends(get_db)]

def login(data, db: Session):
    user = authenticate_user(data, db)
    token = create_token(user.email, str(user.id), timedelta(minutes=720))
    roles = []
    for user_role in getattr(user, "roles", []) or []:
        role = getattr(user_role, "role", None)
        role_name = getattr(role, "name", None)
        if role_name:
            roles.append(role_name)
    logger.info("Login succeeded for %s (id=%s)", user.email, user.id)
    return {
        "access_token": token,
        "token_type": "bearer",
        "roles": roles,
    }

def authenticate_user(data, db: Session):
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if _is_legacy_bcrypt_hash(user.password):
        return _authenticate_legacy_bcrypt_user(user, data.password, db)
    try:
        if not bcrypt_context.verify(data.password, user.password):
            raise HTTPException(status_code=401, detail="Invalid credentials")
    except (MissingBackendError, UnknownHashError, ValueError) as exc:
        logger.exception("Password verification failed for %s", data.email)
        raise HTTPException(
            status_code=500,
            detail="Password verification failed on the server.",
        ) from exc

    return user

def _is_legacy_bcrypt_hash(password_hash: Optional[str]) -> bool:
    return bool(password_hash) and password_hash.startswith(("$2a$", "$2b$", "$2y$"))

def _authenticate_legacy_bcrypt_user(user: User, password: str, db: Session) -> User:
    """Accounts migrated from the standalone external-certification app keep
    their bcrypt hash until their first login here, which re-hashes it with
    argon2. Checked with the bcrypt library directly: passlib 1.7.4's bcrypt
    handler fails against bcrypt>=5."""
    if not bcrypt.checkpw(password.encode(), user.password.encode()):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user.password = bcrypt_context.hash(password)
    db.commit()
    logger.info("Upgraded legacy bcrypt password hash to argon2 for %s", user.email)
    return user

def create_token(email: str, user_id: str, expires_delta: timedelta):
    secret = os.getenv("JWT_SECRET_KEY")
    algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    if not secret:
        raise HTTPException(status_code=500, detail="JWT secret is not configured.")
    if not algorithm:
        algorithm = "HS256"
    encode = {"sub": email, "user_id": user_id}
    expires = datetime.now() + expires_delta
    encode.update({"exp": expires})
    try:
        return jwt.encode(encode, key=secret, algorithm=algorithm)
    except Exception as exc:
        logger.exception("Failed to create JWT token for %s", email)
        raise HTTPException(status_code=500, detail="Failed to create access token.") from exc

def reset_password(data: UserUpdatePassword, db: Session):
    user = db.query(User).filter(User.email == data.email).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if data.new_password != data.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    user.password = bcrypt_context.hash(data.new_password)
    db.commit()
    db.refresh(user)
    return {"message": "Password has been reset successfully"}

def get_current_user(
    token: str = Depends(oauth2_bearer),
    db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            os.getenv("JWT_SECRET_KEY"),
            algorithms=[os.getenv("JWT_ALGORITHM")]
        )

        user_id = payload.get("user_id")
        if user_id is None:
            raise credentials_exception

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token has expired"
        )
    except jwt.InvalidTokenError:
        raise credentials_exception

    # Fetch user
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise credentials_exception

    return user

def verify_token(token: str, db: Session) -> Optional[User]:
    """
    Verify JWT token and return user.
    Returns None if token is invalid or expired.
    Used for WebSocket authentication.
    """
    try:
        payload = jwt.decode(
            token,
            os.getenv("JWT_SECRET_KEY"),
            algorithms=[os.getenv("JWT_ALGORITHM")]
        )

        user_id = payload.get("user_id")
        if user_id is None:
            return None

        # Fetch user
        user = db.query(User).filter(User.id == user_id).first()
        return user

    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
    except Exception:
        return None
