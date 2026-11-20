from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.question import Question
from app.models.questionnaire import Questionnaire
from app.models.user import User
from app.schemas.schema import QuestionCreate, QuestionSchema, QuestionUpdate
from app.services.checklist_change_request_service import submit_change_request
from app.services.role_access_service import (
    has_admin_role,
    has_quality_manager_role,
    is_restricted_auditor,
)


def _requires_approval(current_user: User | None) -> bool:
    return bool(current_user and is_restricted_auditor(current_user))


def _can_add_new_question(current_user: User | None) -> bool:
    if current_user is None:
        return True
    return bool(
        current_user
        and (
            has_admin_role(current_user)
            or has_quality_manager_role(current_user)
            or is_restricted_auditor(current_user)
        )
    )


def _can_edit_existing_questions(current_user: User | None) -> bool:
    if current_user is None:
        return True
    return bool(
        current_user
        and (
            has_admin_role(current_user)
            or has_quality_manager_role(current_user)
            or is_restricted_auditor(current_user)
        )
    )


def _is_owner_under_revision_draft(
    questionnaire: Questionnaire, current_user: User | None
) -> bool:
    if not current_user:
        return False
    if questionnaire.created_by != current_user.id:
        return False
    return (questionnaire.status or "").strip().lower() == "under revision"


def _assert_auditor_can_edit_questionnaire(
    questionnaire: Questionnaire, current_user: User | None
) -> None:
    if not _requires_approval(current_user):
        return

    if questionnaire.created_by != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Auditor can only modify questions in their own Under Revision questionnaires.",
        )

    if (questionnaire.status or "").strip().lower() != "under revision":
        raise HTTPException(
            status_code=400,
            detail="Auditor can modify questions only in Under Revision questionnaires.",
        )


def _assert_auditor_can_request_change(
    questionnaire: Questionnaire, current_user: User | None
) -> None:
    if not _requires_approval(current_user):
        return
    if not current_user:
        raise HTTPException(status_code=403, detail="User is required.")

    status = (questionnaire.status or "").strip().lower()
    if status != "ready to use":
        raise HTTPException(
            status_code=400,
            detail=(
                "Auditor can request changes only for Ready to Use questionnaires. "
                "Own Under Revision draft can be edited directly."
            ),
        )


def _is_iatf_pm_questionnaire(questionnaire: Questionnaire) -> bool:
    name = (questionnaire.name or "").strip().lower()
    return "plant manager" in name and "iatf" in name


def _validate_pm_mandatory_weight(weight: int | None) -> None:
    if weight not in (0, 1):
        raise HTTPException(
            status_code=400,
            detail="For Plant Manager IATF questionnaires, 'weight' must be 0 (non-mandatory) or 1 (mandatory).",
        )


def _bump_questionnaire_version(questionnaire: Questionnaire) -> None:
    questionnaire.version = (questionnaire.version or 0) + 1


def _question_snapshot(question: Question) -> dict:
    return {
        "id": question.id,
        "description": question.description,
        "chapter": question.chapter,
        "weight": question.weight,
        "critical_value": question.critical_value,
        "question_code": question.question_code,
        "element": question.element,
        "subgroup": question.subgroup,
        "is_asterisk": question.is_asterisk,
    }


def _request_response_message(action_label: str) -> str:
    return (
        f"Question {action_label} request submitted to Quality Manager for approval."
    )


def create_question(
    data: QuestionCreate,
    questionnaire_id: int,
    db: Session,
    current_user: User | None = None,
    request_comment: str | None = None,
):
    if not _can_add_new_question(current_user):
        raise HTTPException(
            status_code=403,
            detail="You are not allowed to add new questions.",
        )

    # 1. Verify questionnaire exists
    questionnaire = db.query(Questionnaire).filter_by(id=questionnaire_id).first()
    if not questionnaire:
        raise HTTPException(status_code=404, detail="Questionnaire not found")

    # 2. (Optional) check duplicate per questionnaire
    existing_q = db.query(Question).filter_by(
        description=data.description,
        questionnaire_id=questionnaire_id
    ).first()

    if existing_q:
        raise HTTPException(status_code=400, detail="Question already exists in this questionnaire")

    if _is_iatf_pm_questionnaire(questionnaire):
        _validate_pm_mandatory_weight(data.weight)

    if _requires_approval(current_user):
        if _is_owner_under_revision_draft(questionnaire, current_user):
            _assert_auditor_can_edit_questionnaire(questionnaire, current_user)
        else:
            _assert_auditor_can_request_change(questionnaire, current_user)
            payload = data.model_dump(exclude_none=True)
            payload["questions"] = [data.model_dump(exclude_none=True)]
            request = submit_change_request(
                db=db,
                requested_by=current_user,
                entity_type="question",
                action_type="create",
                questionnaire_id=questionnaire.id,
                target_id=None,
                payload=payload,
                request_comment=request_comment
                or "Auditor requested a new question addition.",
            )
            return {
                "message": _request_response_message("creation"),
                "requires_approval": True,
                "request_id": request.id,
            }

    # 3. Create new Question with direct FK
    new_q = Question(
        **data.model_dump(),
        questionnaire_id=questionnaire_id
    )

    db.add(new_q)
    _bump_questionnaire_version(questionnaire)
    db.commit()
    db.refresh(new_q)

    return new_q



def get_question(question_id: int, db: Session):
    q = db.query(Question).filter_by(id=question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    return q


def list_questions(db: Session):
    return db.query(Question).all()


def update_question(
    question_id: int,
    data: QuestionUpdate,
    db: Session,
    current_user: User | None = None,
    request_comment: str | None = None,
):
    if not _can_edit_existing_questions(current_user):
        raise HTTPException(
            status_code=403,
            detail="You are not allowed to update questionnaire questions.",
        )

    q = db.query(Question).filter_by(id=question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")
    incoming = data.model_dump(exclude_unset=True)
    if not incoming:
        raise HTTPException(status_code=400, detail="No fields provided for update.")

    if _is_iatf_pm_questionnaire(q.questionnaire):
        if "weight" in incoming:
            _validate_pm_mandatory_weight(incoming.get("weight"))

    if _requires_approval(current_user):
        if _is_owner_under_revision_draft(q.questionnaire, current_user):
            _assert_auditor_can_edit_questionnaire(q.questionnaire, current_user)
        else:
            _assert_auditor_can_request_change(q.questionnaire, current_user)
            before = _question_snapshot(q)
            after = {**before, **incoming}
            payload = {
                "question_id": q.id,
                "before": before,
                "after": after,
                "questions": [after],
            }
            request = submit_change_request(
                db=db,
                requested_by=current_user,
                entity_type="question",
                action_type="update",
                questionnaire_id=q.questionnaire_id,
                target_id=q.id,
                payload=payload,
                request_comment=request_comment or "Auditor requested a question update.",
            )
            return {
                "message": _request_response_message("update"),
                "requires_approval": True,
                "request_id": request.id,
            }

    changed = False
    for key, value in incoming.items():
        if getattr(q, key) != value:
            setattr(q, key, value)
            changed = True

    if changed:
        _bump_questionnaire_version(q.questionnaire)

    db.commit()
    db.refresh(q)
    return q


def delete_question(
    question_id: int,
    db: Session,
    current_user: User | None = None,
    request_comment: str | None = None,
):
    if not _can_edit_existing_questions(current_user):
        raise HTTPException(
            status_code=403,
            detail="You are not allowed to delete questionnaire questions.",
        )

    q = db.query(Question).filter_by(id=question_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    if _requires_approval(current_user):
        if _is_owner_under_revision_draft(q.questionnaire, current_user):
            _assert_auditor_can_edit_questionnaire(q.questionnaire, current_user)
        else:
            _assert_auditor_can_request_change(q.questionnaire, current_user)
            deleted_snapshot = _question_snapshot(q)
            payload = {
                "question_id": q.id,
                "deleted_question": deleted_snapshot,
                "questions": [deleted_snapshot],
            }
            request = submit_change_request(
                db=db,
                requested_by=current_user,
                entity_type="question",
                action_type="delete",
                questionnaire_id=q.questionnaire_id,
                target_id=q.id,
                payload=payload,
                request_comment=request_comment
                or "Auditor requested question deletion.",
            )
            return {
                "message": _request_response_message("deletion"),
                "requires_approval": True,
                "request_id": request.id,
            }

    _bump_questionnaire_version(q.questionnaire)
    db.delete(q)
    db.commit()
    return {"message": f"Question {question_id} deleted"}


def get_questions_by_questionnaire(questionnaire_id: int, db: Session):
    questionnaire = db.query(Questionnaire).filter_by(id=questionnaire_id).first()
    if not questionnaire:
        raise HTTPException(status_code=404, detail="Questionnaire not found")

    if not questionnaire.questions:
        raise HTTPException(status_code=404, detail="No questions found for this questionnaire")

    return [
        QuestionSchema.model_validate(q)
        for q in questionnaire.questions
    ]

