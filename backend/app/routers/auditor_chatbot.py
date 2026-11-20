"""Auditor assistant chat - auditors, quality managers and admins."""

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.models.user import User
from app.services import auditor_chatbot_service
from app.services.auth_service import get_current_user

router = APIRouter(prefix="/auditor-chatbot", tags=["Auditor Chatbot"])


def assistant_user(current_user: User = Depends(get_current_user)) -> User:
    if not auditor_chatbot_service.can_use_assistant(current_user):
        raise HTTPException(status_code=403, detail="Auditor, quality manager or admin access required.")
    return current_user


class ChatMessageIn(BaseModel):
    message: str


@router.get("/history")
def get_history(user: User = Depends(assistant_user), db: Session = Depends(get_db)):
    return auditor_chatbot_service.get_chat_history(user, db)


@router.post("/message")
def post_message(
    payload: ChatMessageIn, user: User = Depends(assistant_user), db: Session = Depends(get_db)
):
    return auditor_chatbot_service.send_message(user, db, payload.message)


@router.delete("/history", status_code=204)
def delete_history(user: User = Depends(assistant_user), db: Session = Depends(get_db)):
    auditor_chatbot_service.clear_chat_history(user, db)
    return Response(status_code=204)
