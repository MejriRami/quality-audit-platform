from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.config.database import get_db
from app.services import auth_service, question_service
from app.schemas.schema import QuestionCreate, QuestionUpdate, QuestionOut

router = APIRouter(
    prefix="/question",
    tags=["Questions"],
    dependencies=[Depends(auth_service.get_current_user)],
)


@router.post("/{questionnaire_id}")
def create_question(
    question: QuestionCreate,
    questionnaire_id: int,
    request_comment: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    return question_service.create_question(
        question,
        questionnaire_id,
        db,
        current_user,
        request_comment=request_comment,
    )


@router.get("/{question_id}", response_model=QuestionOut)
def get_question(question_id: int, db: Session = Depends(get_db)):
    return question_service.get_question(question_id, db)


@router.get("/", response_model=List[QuestionOut])
def list_questions(db: Session = Depends(get_db)):
    return question_service.list_questions(db)


@router.put("/{question_id}")
def update_question(
    question_id: int,
    data: QuestionUpdate,
    request_comment: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    return question_service.update_question(
        question_id,
        data,
        db,
        current_user,
        request_comment=request_comment,
    )


@router.delete("/{question_id}")
def delete_question(
    question_id: int,
    request_comment: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    return question_service.delete_question(
        question_id,
        db,
        current_user,
        request_comment=request_comment,
    )


@router.get("/getAll/{questionnaire_id}")
def get_questions_by_questionnaire(questionnaire_id: int, db: Session = Depends(get_db)):
    return question_service.get_questions_by_questionnaire(questionnaire_id, db)
