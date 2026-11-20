import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.audit_type import AuditType
from app.models.checklist_change_request import ChecklistChangeRequest
from app.models.framework import Framework
from app.models.notification import Notification
from app.models.questionnaire import Questionnaire
from app.models.questionnaire_auditor import QuestionnaireAuditor
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole
from app.schemas.QuestionnaireSchema import QuestionnaireCreate
from app.schemas.schema import QuestionCreate, QuestionUpdate
from app.config.connection_manager import manager
from app.services.role_access_service import ADMIN_ROLE_NAMES, is_admin_or_quality_manager


def _json_default(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def set_questionnaire_under_revision(db: Session, questionnaire_id: Optional[int]) -> None:
    if not questionnaire_id:
        return
    q = db.query(Questionnaire).filter(Questionnaire.id == questionnaire_id).first()
    if q:
        q.status = "Under Revision"
        db.flush()


def set_questionnaire_ready_to_use(db: Session, questionnaire_id: Optional[int]) -> None:
    if not questionnaire_id:
        return
    q = db.query(Questionnaire).filter(Questionnaire.id == questionnaire_id).first()
    if q:
        q.status = "Ready to Use"
        db.flush()


def _has_other_pending_requests(
    db: Session, questionnaire_id: Optional[int], exclude_request_id: Optional[int] = None
) -> bool:
    if not questionnaire_id:
        return False
    query = db.query(ChecklistChangeRequest).filter(
        ChecklistChangeRequest.questionnaire_id == questionnaire_id,
        ChecklistChangeRequest.status == "pending",
    )
    if exclude_request_id is not None:
        query = query.filter(ChecklistChangeRequest.id != exclude_request_id)
    return query.first() is not None


def _update_questionnaire_status_after_resolution(
    db: Session, questionnaire_id: Optional[int], resolved_request_id: Optional[int] = None
) -> None:
    if not questionnaire_id:
        return
    if _has_other_pending_requests(db, questionnaire_id, exclude_request_id=resolved_request_id):
        set_questionnaire_under_revision(db, questionnaire_id)
    else:
        set_questionnaire_ready_to_use(db, questionnaire_id)


def _sync_questionnaire_status_after_decision(
    db: Session,
    request: ChecklistChangeRequest,
    approved: bool,
) -> None:
    questionnaire_id = request.questionnaire_id
    if not questionnaire_id:
        return

    entity_type = (request.entity_type or "").strip().lower()
    action_type = (request.action_type or "").strip().lower()

    # Question-level requests should keep Ready-to-Use lifecycle intact.
    if entity_type == "question":
        if not _has_other_pending_requests(
            db,
            questionnaire_id,
            exclude_request_id=request.id,
        ):
            set_questionnaire_ready_to_use(db, questionnaire_id)
        return

    if entity_type != "questionnaire":
        return

    # Draft submission flow: approval promotes draft, rejection keeps draft editable.
    if action_type == "submit":
        if approved:
            set_questionnaire_ready_to_use(db, questionnaire_id)
        else:
            set_questionnaire_under_revision(db, questionnaire_id)
        return

    _update_questionnaire_status_after_resolution(
        db=db,
        questionnaire_id=questionnaire_id,
        resolved_request_id=request.id,
    )


def _quality_manager_user_ids(db: Session) -> list[int]:
    roles = list(ADMIN_ROLE_NAMES)
    rows = (
        db.query(UserRole.user_id)
        .join(Role, Role.id == UserRole.role_id)
        .filter(func.lower(Role.name).in_(roles))
        .distinct()
        .all()
    )
    return [r[0] for r in rows]


def _notify_quality_managers(
    db: Session,
    request: ChecklistChangeRequest,
    requested_by: User,
) -> list[Notification]:
    reviewer_ids = _quality_manager_user_ids(db)
    if not reviewer_ids:
        return []

    requester_email = getattr(requested_by, "email", "unknown")
    title = "Checklist change approval required"
    message = (
        f"{requester_email} requested to {request.action_type} "
        f"{request.entity_type}. Review request #{request.id}."
    )
    link = f"/questionnaire?tab=requests&request_id={request.id}&status=pending"
    meta_json = json.dumps(
        {
            "request_id": request.id,
            "entity_type": request.entity_type,
            "action_type": request.action_type,
            "questionnaire_id": request.questionnaire_id,
            "status": "pending",
            "tab": "requests",
        }
    )

    created_notifications: list[Notification] = []
    for reviewer_id in reviewer_ids:
        notification = Notification(
            user_id=reviewer_id,
            type="checklist_change_request",
            title=title,
            message=message,
            link=link,
            read=False,
            created_at=datetime.now(timezone.utc),
            meta_data=meta_json,
        )
        db.add(notification)
        created_notifications.append(notification)
    return created_notifications


def _notification_metadata(raw_meta: Optional[str]) -> Optional[dict[str, Any]]:
    if not raw_meta:
        return None
    try:
        parsed = json.loads(raw_meta)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _push_ws_notification(notification: Notification) -> None:
    payload = {
        "id": notification.id,
        "type": notification.type,
        "title": notification.title,
        "message": notification.message,
        "link": notification.link,
        "metadata": _notification_metadata(notification.meta_data),
        "read": bool(notification.read),
        "created_at": notification.created_at.isoformat()
        if notification.created_at
        else datetime.now(timezone.utc).isoformat(),
    }
    asyncio.run(manager.send_personal_notification(notification.user_id, payload))


def _notify_requester(
    db: Session,
    request: ChecklistChangeRequest,
    approved: bool,
    review_comment: Optional[str] = None,
) -> Notification:
    status_text = "approved" if approved else "rejected"
    comment_text = f" Comment: {review_comment}" if review_comment else ""
    notification = Notification(
        user_id=request.requested_by_id,
        type="checklist_change_request_decision",
        title=f"Checklist change request {status_text}",
        message=(
            f"Your request #{request.id} to {request.action_type} "
            f"{request.entity_type} was {status_text}.{comment_text}"
        ),
        link=(
            f"/questionnaire?tab=requests&request_id={request.id}"
            f"&status={status_text}"
        ),
        read=False,
        created_at=datetime.now(timezone.utc),
        meta_data=json.dumps(
            {
                "request_id": request.id,
                "status": status_text,
                "questionnaire_id": request.questionnaire_id,
                "tab": "requests",
            }
        ),
    )
    db.add(notification)
    return notification


def submit_change_request(
    db: Session,
    requested_by: User,
    entity_type: str,
    action_type: str,
    questionnaire_id: Optional[int] = None,
    target_id: Optional[int] = None,
    payload: Optional[dict[str, Any]] = None,
    request_comment: Optional[str] = None,
) -> ChecklistChangeRequest:
    request = ChecklistChangeRequest(
        entity_type=entity_type,
        action_type=action_type,
        status="pending",
        questionnaire_id=questionnaire_id,
        target_id=target_id,
        payload=(
            json.dumps(payload, ensure_ascii=True, default=_json_default)
            if payload
            else None
        ),
        requested_by_id=requested_by.id,
        request_comment=request_comment,
        created_at=datetime.now(timezone.utc),
    )
    db.add(request)
    db.flush()
    if (entity_type or "").strip().lower() == "questionnaire":
        set_questionnaire_under_revision(db, questionnaire_id)

    created_notifications = _notify_quality_managers(db, request, requested_by)
    db.commit()
    db.refresh(request)
    for notification in created_notifications:
        _push_ws_notification(notification)
    return request


def _user_display_name(user: Optional[User]) -> Optional[str]:
    if not user:
        return None
    first_name = (getattr(user, "first_name", "") or "").strip()
    last_name = (getattr(user, "last_name", "") or "").strip()
    full_name = " ".join(part for part in [first_name, last_name] if part).strip()
    return full_name or None


def _to_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _question_preview(questions: Any, max_items: int = 5) -> list[dict[str, Any]]:
    if not isinstance(questions, list):
        return []
    preview: list[dict[str, Any]] = []
    for q in questions[:max_items]:
        if not isinstance(q, dict):
            continue
        preview.append(
            {
                "id": q.get("id"),
                "description": q.get("description"),
                "chapter": q.get("chapter"),
                "weight": q.get("weight"),
                "critical_value": q.get("critical_value"),
            }
        )
    return preview


def _build_questionnaire_context(
    db: Session,
    request: ChecklistChangeRequest,
    payload: Optional[dict[str, Any]],
) -> dict[str, Any]:
    payload = payload or {}
    questionnaire = request.questionnaire

    questionnaire_id = (
        _to_int(payload.get("id"))
        or request.questionnaire_id
        or request.target_id
        or getattr(questionnaire, "id", None)
    )
    version = payload.get("version") or getattr(questionnaire, "version", None)
    status = payload.get("status") or getattr(questionnaire, "status", None)
    target_duration = payload.get("target_duration") or getattr(
        questionnaire, "target_duration", None
    )
    if hasattr(target_duration, "isoformat"):
        target_duration = target_duration.isoformat()
    elif target_duration is not None:
        target_duration = str(target_duration)

    framework_id = _to_int(payload.get("framework_id")) or getattr(
        questionnaire, "framework_id", None
    )
    framework_obj = getattr(questionnaire, "framework", None)
    if framework_id and (
        framework_obj is None or getattr(framework_obj, "id", None) != framework_id
    ):
        framework_obj = (
            db.query(Framework).filter(Framework.id == framework_id).first()
        )

    type_id = _to_int(payload.get("type_id")) or getattr(questionnaire, "type_id", None)
    audit_type_obj = getattr(questionnaire, "audit_type", None)
    if type_id and (audit_type_obj is None or getattr(audit_type_obj, "id", None) != type_id):
        audit_type_obj = db.query(AuditType).filter(AuditType.id == type_id).first()

    auditor_emails = payload.get("auditor_emails")
    if not isinstance(auditor_emails, list):
        auditor_emails = [
            qa.auditor.email
            for qa in (getattr(questionnaire, "auditors", None) or [])
            if getattr(qa, "auditor", None) and getattr(qa.auditor, "email", None)
        ]

    payload_questions = payload.get("questions")
    questions_count = None
    questions_preview: list[dict[str, Any]] = []

    if isinstance(payload_questions, list):
        questions_count = len(payload_questions)
        questions_preview = _question_preview(payload_questions)
    elif questionnaire is not None:
        questions = getattr(questionnaire, "questions", None) or []
        questions_count = len(questions)
        questions_preview = [
            {
                "id": q.id,
                "description": q.description,
                "chapter": q.chapter,
                "weight": q.weight,
                "critical_value": q.critical_value,
            }
            for q in questions[:5]
        ]

    return {
        "id": questionnaire_id,
        "name": payload.get("name") or getattr(questionnaire, "name", None),
        "version": version,
        "status": status,
        "target_duration": target_duration,
        "framework": {
            "id": framework_id or getattr(framework_obj, "id", None),
            "code": payload.get("framework_code") or getattr(framework_obj, "code", None),
            "label": payload.get("framework_label") or getattr(framework_obj, "label", None),
        },
        "audit_type": {
            "id": type_id or getattr(audit_type_obj, "id", None),
            "value": payload.get("audit_type") or getattr(audit_type_obj, "value", None),
        },
        "auditor_emails": auditor_emails,
        "questions_count": questions_count,
        "questions_preview": questions_preview,
    }


def _build_request_summary(request: ChecklistChangeRequest, questionnaire_name: Optional[str]) -> str:
    action = (request.action_type or "").replace("_", " ").strip().title()
    entity = (request.entity_type or "").replace("_", " ").strip().title()
    if questionnaire_name:
        return f"{action} {entity}: {questionnaire_name}"
    return f"{action} {entity}"


def list_change_requests(db: Session, current_user: User, status: Optional[str] = None) -> list[dict[str, Any]]:
    query = (
        db.query(ChecklistChangeRequest)
        .options(
            joinedload(ChecklistChangeRequest.requested_by),
            joinedload(ChecklistChangeRequest.reviewed_by),
            joinedload(ChecklistChangeRequest.questionnaire).joinedload(Questionnaire.framework),
            joinedload(ChecklistChangeRequest.questionnaire).joinedload(Questionnaire.audit_type),
            joinedload(ChecklistChangeRequest.questionnaire)
            .joinedload(Questionnaire.auditors)
            .joinedload(QuestionnaireAuditor.auditor),
            joinedload(ChecklistChangeRequest.questionnaire).joinedload(Questionnaire.questions),
        )
        .order_by(ChecklistChangeRequest.created_at.desc())
    )

    if status:
        query = query.filter(ChecklistChangeRequest.status == status)

    if not is_admin_or_quality_manager(current_user):
        query = query.filter(ChecklistChangeRequest.requested_by_id == current_user.id)

    requests = query.all()
    items: list[dict[str, Any]] = []
    for r in requests:
        payload: Optional[dict[str, Any]] = None
        if r.payload:
            try:
                parsed_payload = json.loads(r.payload)
                payload = parsed_payload if isinstance(parsed_payload, dict) else None
            except Exception:
                payload = None

        questionnaire_context = _build_questionnaire_context(db, r, payload)
        questionnaire_name = questionnaire_context.get("name")
        status_label = (r.status or "").replace("_", " ").strip().title()

        items.append(
            {
                "id": r.id,
                "entity_type": r.entity_type,
                "action_type": r.action_type,
                "status": r.status,
                "status_label": status_label,
                "summary": _build_request_summary(r, questionnaire_name),
                "questionnaire_id": r.questionnaire_id,
                "target_id": r.target_id,
                "payload": payload,
                "questionnaire_context": questionnaire_context,
                "request_comment": r.request_comment,
                "review_comment": r.review_comment,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
                "applied_at": r.applied_at.isoformat() if r.applied_at else None,
                "requested_by": {
                    "id": r.requested_by_id,
                    "email": getattr(r.requested_by, "email", None),
                    "name": _user_display_name(r.requested_by),
                },
                "reviewed_by": {
                    "id": r.reviewed_by_id,
                    "email": getattr(r.reviewed_by, "email", None),
                    "name": _user_display_name(r.reviewed_by),
                }
                if r.reviewed_by_id
                else None,
            }
        )
    return items


def _apply_request_payload(db: Session, request: ChecklistChangeRequest) -> Optional[int]:
    payload = json.loads(request.payload) if request.payload else {}

    if request.entity_type == "questionnaire":
        from app.services import questionnaire_service

        if request.action_type == "submit":
            questionnaire_id = request.target_id or request.questionnaire_id
            if not questionnaire_id:
                raise HTTPException(
                    status_code=400,
                    detail="Submitted questionnaire request is missing questionnaire id.",
                )
            return questionnaire_id

        if request.action_type == "create":
            # Preferred flow: questionnaire already exists in Under Revision;
            # approval promotes it to Ready to Use.
            existing_id = request.target_id or request.questionnaire_id
            if existing_id:
                questionnaire_service.update_questionnaire_fields_sync(
                    questionnaire_id=existing_id,
                    data=payload,
                    db=db,
                    force_ready_status=False,
                )
                return existing_id

            # Backward compatibility for older pending requests without target_id.
            payload["status"] = "Ready to Use"
            created = questionnaire_service.create_questionnaire(
                QuestionnaireCreate.model_validate(payload),
                db,
            )
            questionnaire_id = created.get("questionnaire", {}).get("id")
            return questionnaire_id

        if request.action_type == "update":
            questionnaire_service.update_questionnaire_fields_sync(
                questionnaire_id=request.target_id,
                data=payload,
                db=db,
                force_ready_status=True,
            )
            return request.target_id

        if request.action_type == "delete":
            questionnaire_service.delete_questionnaire(request.target_id, db)
            return None

    if request.entity_type == "question":
        from app.services import question_service

        questionnaire_id = request.questionnaire_id

        if request.action_type == "create":
            create_payload = payload
            if not isinstance(create_payload, dict):
                raise HTTPException(status_code=400, detail="Invalid create question payload.")
            if "description" not in create_payload:
                candidate = (create_payload.get("after") or {})
                if isinstance(candidate, dict):
                    create_payload = candidate
            question_service.create_question(
                QuestionCreate.model_validate(create_payload),
                questionnaire_id=questionnaire_id,
                db=db,
                current_user=None,
            )
            return questionnaire_id

        if request.action_type == "update":
            update_payload = payload.get("after") if isinstance(payload, dict) else payload
            if not isinstance(update_payload, dict):
                raise HTTPException(status_code=400, detail="Invalid update question payload.")
            update_fields = {
                key: update_payload.get(key)
                for key in ["description", "chapter", "weight", "critical_value"]
                if key in update_payload
            }
            if not update_fields:
                raise HTTPException(
                    status_code=400,
                    detail="Update request has no editable question fields.",
                )
            question_service.update_question(
                question_id=request.target_id,
                data=QuestionUpdate.model_validate(update_fields),
                db=db,
                current_user=None,
            )
            return questionnaire_id

        if request.action_type == "delete":
            question_service.delete_question(
                question_id=request.target_id,
                db=db,
                current_user=None,
            )
            return questionnaire_id

    raise HTTPException(status_code=400, detail="Unsupported change request payload.")


def approve_change_request(
    db: Session,
    request_id: int,
    reviewer: User,
    review_comment: Optional[str] = None,
) -> dict[str, Any]:
    if not is_admin_or_quality_manager(reviewer):
        raise HTTPException(status_code=403, detail="Only Quality Manager/Admin can approve requests.")

    request = db.query(ChecklistChangeRequest).filter(ChecklistChangeRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Change request not found.")
    if request.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending requests can be approved.")

    try:
        applied_questionnaire_id = _apply_request_payload(db, request)
        request.status = "approved"
        request.reviewed_by_id = reviewer.id
        request.review_comment = review_comment
        request.reviewed_at = datetime.now(timezone.utc)
        request.applied_at = datetime.now(timezone.utc)
        if applied_questionnaire_id:
            request.questionnaire_id = applied_questionnaire_id
        _sync_questionnaire_status_after_decision(
            db=db,
            request=request,
            approved=True,
        )
        requester_notification = _notify_requester(
            db,
            request,
            approved=True,
            review_comment=review_comment,
        )
        db.commit()
        _push_ws_notification(requester_notification)
    except Exception:
        db.rollback()
        raise

    return {"message": f"Request #{request.id} approved and applied.", "id": request.id}


def reject_change_request(
    db: Session,
    request_id: int,
    reviewer: User,
    review_comment: Optional[str] = None,
) -> dict[str, Any]:
    if not is_admin_or_quality_manager(reviewer):
        raise HTTPException(status_code=403, detail="Only Quality Manager/Admin can reject requests.")

    request = db.query(ChecklistChangeRequest).filter(ChecklistChangeRequest.id == request_id).first()
    if not request:
        raise HTTPException(status_code=404, detail="Change request not found.")
    if request.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending requests can be rejected.")

    request.status = "rejected"
    request.reviewed_by_id = reviewer.id
    request.review_comment = review_comment
    request.reviewed_at = datetime.now(timezone.utc)
    _sync_questionnaire_status_after_decision(
        db=db,
        request=request,
        approved=False,
    )
    requester_notification = _notify_requester(
        db,
        request,
        approved=False,
        review_comment=review_comment,
    )
    db.commit()
    _push_ws_notification(requester_notification)

    return {"message": f"Request #{request.id} rejected.", "id": request.id}
