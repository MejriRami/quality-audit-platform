from typing import  Optional
from sqlalchemy import exists
from sqlalchemy.orm import Session
from fastapi import HTTPException, UploadFile

from app.models.audit import Audit
from app.models.audit_type import AuditType
from app.models.checklist_change_request import ChecklistChangeRequest
from app.models.document import Document
from app.models.framework import Framework
from app.models.questionnaire import Questionnaire
from app.models.questionnaire_auditor import QuestionnaireAuditor
from app.models.role import Role
from app.models.user import User
from app.models.user_role import UserRole
from app.schemas.QuestionnaireSchema import QuestionnaireCreate
from sqlalchemy.orm import joinedload
from datetime import datetime, timezone

from app.services.sharepoint_audit_storage import SharePointGuidelineStorage
from app.services.scoring_service import infer_default_score_calculation
from app.services.checklist_change_request_service import (
    submit_change_request,
)
from app.services.role_access_service import (
    can_manage_questionnaires,
    has_auditor_role,
    is_admin_or_quality_manager,
    is_restricted_auditor,
)


def _requires_approval(current_user: Optional[User]) -> bool:
    return bool(current_user and is_restricted_auditor(current_user))


def _assert_can_manage_questionnaires(current_user: Optional[User]) -> None:
    if current_user and can_manage_questionnaires(current_user):
        return
    raise HTTPException(
        status_code=403,
        detail="Only auditors, quality managers, and admins can manage questionnaires.",
    )


def _user_payload(user: Optional[User]) -> Optional[dict]:
    if not user:
        return None
    first_name = (getattr(user, "first_name", "") or "").strip()
    last_name = (getattr(user, "last_name", "") or "").strip()
    return {
        "id": user.id,
        "email": user.email,
        "name": " ".join(part for part in [first_name, last_name] if part).strip()
        or None,
    }


def _latest_approved_requests_by_questionnaire(
    db: Session, questionnaire_ids: list[int]
) -> dict[int, ChecklistChangeRequest]:
    if not questionnaire_ids:
        return {}

    rows = (
        db.query(ChecklistChangeRequest)
        .options(joinedload(ChecklistChangeRequest.reviewed_by))
        .filter(
            ChecklistChangeRequest.entity_type == "questionnaire",
            ChecklistChangeRequest.status == "approved",
            ChecklistChangeRequest.questionnaire_id.in_(questionnaire_ids),
        )
        .order_by(
            ChecklistChangeRequest.questionnaire_id.asc(),
            ChecklistChangeRequest.reviewed_at.desc(),
            ChecklistChangeRequest.id.desc(),
        )
        .all()
    )
    latest: dict[int, ChecklistChangeRequest] = {}
    for row in rows:
        qid = row.questionnaire_id
        if qid and qid not in latest:
            latest[qid] = row
    return latest

def create_questionnaire(data: QuestionnaireCreate, db: Session, created_by: Optional[int] = None):
    # Check name uniqueness
    existing = db.query(Questionnaire).filter_by(name=data.name).first()
    if existing:
        raise HTTPException(status_code=400, detail="Questionnaire name already exists")

    # Validate framework
    framework = db.query(Framework).filter_by(id=data.framework_id).first()
    if not framework:
        raise HTTPException(status_code=404, detail="Framework not found")

    # Validate type
    if data.type_id is not None:
        audit_type = db.query(AuditType).filter_by(id=data.type_id).first()
        if not audit_type:
            raise HTTPException(status_code=400, detail="Invalid audit Type")
    
    payload = data.model_dump(exclude={"auditor_emails"})
    if not payload.get("score_calculation"):
        payload["score_calculation"] = infer_default_score_calculation(
            questionnaire_name=data.name,
            audit_type_value=audit_type.value if data.type_id is not None else None,
            framework_code=framework.code if framework else None,
            framework_label=framework.label if framework else None,
        )
    # Create questionnaire
    questionnaire = Questionnaire(**payload)
    questionnaire.created_at = datetime.now(timezone.utc)
    if created_by is not None:
        questionnaire.created_by = created_by

    db.add(questionnaire)
    db.commit()
    db.refresh(questionnaire)

    # --- AUDITORS HANDLING ---
    auditors = []

    if data.auditor_emails:
        # Ensure auditor role exists
        auditor_role = db.query(Role).filter(Role.name == "auditor").first()
        if not auditor_role:
            raise HTTPException(
                status_code=500,
                detail="Role 'auditor' not found in roles table."
            )

        for email in data.auditor_emails:
            # Find user
            auditor = db.query(User).filter(User.email == email).first()
            if not auditor:
                raise HTTPException(
                    status_code=404,
                    detail="User not found."
                )

            # Ensure user has auditor role
            has_role = db.query(UserRole).filter(
                UserRole.user_id == auditor.id,
                UserRole.role_id == auditor_role.id
            ).first()

            if not has_role:
                raise HTTPException(
                    status_code=400,
                    detail="User does not have auditor role."
                )

            # Save in return list
            auditors.append({"email": auditor.email})

            # Link to questionnaire
            link = QuestionnaireAuditor(
                questionnaire_id=questionnaire.id,
                auditor_id=auditor.id
            )
            db.add(link)

        db.commit()

    db.refresh(questionnaire)
    return {
        "message": "Questionnaire added successfully",
        "questionnaire": {
            "id": questionnaire.id,
            "version": questionnaire.version,
            "created_by": questionnaire.created_by,
            "status": questionnaire.status,
            "target_duration": questionnaire.target_duration,
            "score_calculation": questionnaire.score_calculation,
            "auditType": {
                "id": questionnaire.audit_type.id if questionnaire.audit_type else None,
                "value": questionnaire.audit_type.value if questionnaire.audit_type else None,
            },
            "framework": {
                "id": questionnaire.framework.id,
                "label": questionnaire.framework.label,
                "code": questionnaire.framework.code
            } if questionnaire.framework else None,
            "name": questionnaire.name,
            "auditors": auditors
        }
    }


def create_questionnaire_with_access_control(data: QuestionnaireCreate, db: Session, current_user: User):
    _assert_can_manage_questionnaires(current_user)
    if _requires_approval(current_user):
        payload = data.model_dump(exclude_none=True)
        payload["status"] = "Under Revision"
        return create_questionnaire(
            QuestionnaireCreate.model_validate(payload),
            db,
            created_by=current_user.id,
        )

    return create_questionnaire(data, db, created_by=current_user.id if current_user else None)


def get_all_questionnaires(db: Session, current_user: User):
    """
    Get all questionnaires with their related data including guidelines
    """
    query = (
        db.query(Questionnaire)
        .options(
            joinedload(Questionnaire.framework),
            joinedload(Questionnaire.audit_type),
            joinedload(Questionnaire.creator),
            joinedload(Questionnaire.auditors).joinedload(QuestionnaireAuditor.auditor),
            joinedload(Questionnaire.questions),
            joinedload(Questionnaire.guideline),
        )
    )

    if has_auditor_role(current_user) and not is_admin_or_quality_manager(current_user):
        assigned_to_current_user = (
            db.query(QuestionnaireAuditor.questionnaire_id)
            .filter(
                QuestionnaireAuditor.questionnaire_id == Questionnaire.id,
                QuestionnaireAuditor.auditor_id == current_user.id,
            )
            .exists()
        )
        query = query.filter(
            (Questionnaire.status == "Ready to Use")
            | (
                (Questionnaire.status == "Under Revision")
                & (
                    (Questionnaire.created_by == current_user.id)
                    | assigned_to_current_user
                )
            )
        )

    results = query.all()

    if not results:
        raise HTTPException(status_code=404, detail="No questionnaires found")

    approved_request_map = _latest_approved_requests_by_questionnaire(
        db, [q.id for q in results]
    )

    # Clean response
    questionnaires = []
    for q in results:
        auditors = [{"email": auditor.auditor.email} for auditor in q.auditors]
        latest_approval = approved_request_map.get(q.id)

        # Build guideline data if it exists
        guideline_data = None
        if q.guideline_id:
            guideline_doc = db.query(Document).filter_by(id=q.guideline_id).first()
            if guideline_doc:
                guideline_data = {
                    "id": guideline_doc.id,
                    "filename": guideline_doc.filename,
                    "size": guideline_doc.size,
                    "mimetype": guideline_doc.mimetype,
                    "file_url": guideline_doc.file_url,
                    "uploaded_at": guideline_doc.uploaded_at.isoformat() if guideline_doc.uploaded_at else None
                }

        questionnaires.append({
            "id": q.id,
            "version": q.version,
            "created_by": q.created_by,
            "created_by_user": _user_payload(q.creator),
            "created_at": q.created_at.isoformat() if q.created_at else None,
            "creation_method": (
                "Submitted for Approval"
                if latest_approval
                and (latest_approval.action_type or "").strip().lower() in {"create", "submit"}
                else "Direct Creation"
            ),
            "approved_by_user": _user_payload(latest_approval.reviewed_by)
            if latest_approval
            else None,
            "approved_at": latest_approval.reviewed_at.isoformat()
            if latest_approval and latest_approval.reviewed_at
            else None,
            "status": q.status,
            "target_duration": q.target_duration,
            "score_calculation": q.score_calculation,
            "auditType": {
                "id": q.audit_type.id if q.audit_type else None,
                "value": q.audit_type.value if q.audit_type else None,
            },
            "framework": {
                "id": q.framework.id,
                "label": q.framework.label,
                "code": q.framework.code
            } if q.framework else None,
            "name": q.name,
            "auditors": auditors,
            "questions": q.questions,
            "guideline": guideline_data  
        })

    return questionnaires


def get_questionnaire(questionnaire_id: int, db: Session):
    """
    Get a single questionnaire with all related data including guideline
    """
    q = (
        db.query(Questionnaire)
        .options(
            joinedload(Questionnaire.framework),
            joinedload(Questionnaire.audit_type),
            joinedload(Questionnaire.auditors)
                .joinedload(QuestionnaireAuditor.auditor)
                .load_only(User.id, User.email),
            joinedload(Questionnaire.questions),
            joinedload(Questionnaire.guideline)  # Add guideline relationship
        )
        .filter_by(id=questionnaire_id)
        .first()
    )

    if not q:
        raise HTTPException(status_code=404, detail="Questionnaire not found")

    auditors_clean = [qa.auditor for qa in q.auditors]
    
    # Build guideline data if it exists
    guideline_data = None
    if q.guideline_id:
        guideline_doc = db.query(Document).filter_by(id=q.guideline_id).first()
        if guideline_doc:
            guideline_data = {
                "id": guideline_doc.id,
                "filename": guideline_doc.filename,
                "size": guideline_doc.size,
                "mimetype": guideline_doc.mimetype,
                "file_url": guideline_doc.file_url,
                "uploaded_at": guideline_doc.uploaded_at.isoformat() if guideline_doc.uploaded_at else None
            }

    response = {
        "id": q.id,
        "name": q.name,
        "target_duration": q.target_duration,
        "created_by": q.created_by,
        "version": q.version,
        "framework_id": q.framework_id,
        "guideline_id": q.guideline_id,
        "score_calculation": q.score_calculation,
        "status": q.status,
        "created_at": q.created_at,
        "type_id": q.type_id,
        "framework": q.framework,
        "audit_type": q.audit_type,
        "auditors": auditors_clean,
        "questions": q.questions,
        "guideline": guideline_data  # Add guideline to response
    }

    return response

async def update_questionnaire_with_sharepoint( questionnaire_id: int,data: dict, db: Session,guideline_storage: SharePointGuidelineStorage,
    guideline_file: Optional[UploadFile] = None,
    remove_existing_guideline: bool = False,
    current_user_id: Optional[int] = None):
    """
    Update questionnaire with optional file upload to SharePoint (no folder ID)
    
    Args:
        questionnaire_id: ID of questionnaire to update
        data: Dictionary containing update fields
        db: Database session
        guideline_storage: SharePoint guideline storage instance
        guideline_file: Optional file to upload
        remove_existing_guideline: Flag to remove existing guideline
        current_user_id: ID of user performing the update
    """
    auditors = []
    has_updates = False
    
    # Retrieve the existing questionnaire
    q = db.query(Questionnaire).filter_by(id=questionnaire_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Questionnaire not found")

    # Update fields if provided in the input data
    if data.get('framework_id') and q.framework_id != data['framework_id']:
        q.framework_id = data['framework_id']
        has_updates = True
    
    if data.get('name') and q.name != data['name']:
        q.name = data['name']
        has_updates = True
    
    if data.get('status') and q.status != data['status']:
        q.status = data['status']
        has_updates = True
    
    if data.get('target_duration'):
        current_duration = str(q.target_duration) if q.target_duration else None
        if current_duration != data['target_duration']:
            has_updates = True
        q.target_duration = data['target_duration']

    if (
        "score_calculation" in data
        and data.get("score_calculation") is not None
        and q.score_calculation != data["score_calculation"]
    ):
        q.score_calculation = data["score_calculation"]
        has_updates = True

    # Handling audit type
    if data.get('type_id'):
        audit_type = db.query(AuditType).filter_by(id=data['type_id']).first()
        if not audit_type:
            raise HTTPException(status_code=400, detail="Invalid audit type")
        if q.type_id != audit_type.id:
            q.type_id = audit_type.id
            has_updates = True

    if not q.score_calculation:
        current_framework = db.query(Framework).filter_by(id=q.framework_id).first() if q.framework_id else None
        current_type = db.query(AuditType).filter_by(id=q.type_id).first() if q.type_id else None
        q.score_calculation = infer_default_score_calculation(
            questionnaire_name=q.name,
            audit_type_value=current_type.value if current_type else None,
            framework_code=current_framework.code if current_framework else None,
            framework_label=current_framework.label if current_framework else None,
        )

    # Handling auditors
    auditor_emails = data.get('auditor_emails')
    if auditor_emails is not None:
        existing_emails = sorted(
            {
                (qa.auditor.email or "").strip().lower()
                for qa in (q.auditors or [])
                if getattr(qa, "auditor", None) and getattr(qa.auditor, "email", None)
            }
        )
        incoming_emails = sorted({(email or "").strip().lower() for email in auditor_emails})
        if existing_emails != incoming_emails:
            has_updates = True
            # Clear existing auditors
            db.query(QuestionnaireAuditor).filter_by(questionnaire_id=questionnaire_id).delete()

            # Add new auditors
            if auditor_emails:
                for email in auditor_emails:
                    auditor = db.query(User).filter_by(email=email).first()
                    if not auditor:
                        raise HTTPException(status_code=404, detail=f"User with email {email} not found")

                    auditors.append({
                        "id": auditor.id,
                        "email": auditor.email
                    })

                    link = QuestionnaireAuditor(
                        questionnaire_id=questionnaire_id,
                        auditor_id=auditor.id
                    )
                    db.add(link)

    # Handle guideline file removal
    if remove_existing_guideline and q.guideline_id:
        has_updates = True
        existing_doc = db.query(Document).filter_by(id=q.guideline_id).first()
        
        if existing_doc:
            # Delete from SharePoint
            try:
                if existing_doc.sharepoint_drive_id and existing_doc.sharepoint_item_id:
                    await guideline_storage.delete_guideline(
                        drive_id=existing_doc.sharepoint_drive_id,
                        item_id=existing_doc.sharepoint_item_id
                    )
            except Exception as e:
                # Log but don't fail if SharePoint delete fails
                print(f"Warning: Failed to delete from SharePoint: {e}")
            
            # Delete from database
            db.delete(existing_doc)
            q.guideline_id = None
            db.flush()

    # Handle guideline file upload
    if guideline_file and guideline_file.filename:
        has_updates = True
        # Validate file size (e.g., max 50MB)
        file_size = 0
        content = await guideline_file.read()
        file_size = len(content)
        await guideline_file.seek(0)  # Reset file pointer
        
        if file_size > 50 * 1024 * 1024:  # 50MB
            raise HTTPException(status_code=400, detail="File size exceeds 50MB limit")
        
        # Remove old guideline if exists
        if q.guideline_id:
            existing_doc = db.query(Document).filter_by(id=q.guideline_id).first()
            
            if existing_doc:
                # Delete from SharePoint
                try:
                    if existing_doc.sharepoint_drive_id and existing_doc.sharepoint_item_id:
                        await guideline_storage.delete_guideline(
                            drive_id=existing_doc.sharepoint_drive_id,
                            item_id=existing_doc.sharepoint_item_id
                        )
                except Exception as e:
                    print(f"Warning: Failed to delete old file from SharePoint: {e}")
                
                # Delete from database
                db.delete(existing_doc)
                db.flush()
        
        # Upload to SharePoint (directly under Questionnaires-guidelines, no ID folder)
        try:
            upload_result = await guideline_storage.upload_guideline_flat(
                file_bytes=content,
                filename=guideline_file.filename,
                content_type=guideline_file.content_type or "application/octet-stream"
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to upload to SharePoint: {str(e)}")
        
        # Create document entry
        document = Document(
            filename=guideline_file.filename,
            mimetype=guideline_file.content_type,
            size=file_size,
            file_url=upload_result['file']['webUrl'],  # Store SharePoint web URL
            sharepoint_site_id=upload_result['site_id'],
            sharepoint_drive_id=upload_result['drive_id'],
            sharepoint_item_id=upload_result['file']['id'],
            sharepoint_path=upload_result['file']['path'],
            uploaded_at=datetime.now(),
            uploaded_by=current_user_id
        )
        
        db.add(document)
        db.flush()
        
        # Update questionnaire with new guideline_id
        q.guideline_id = document.id

    if has_updates:
        q.version = (q.version or 0) + 1

    # Commit the changes to the database
    db.commit()
    db.refresh(q)

    # Build guideline response if exists
    guideline_response = None
    if q.guideline_id:
        guideline_doc = db.query(Document).filter_by(id=q.guideline_id).first()
        if guideline_doc:
            guideline_response = {
                "id": guideline_doc.id,
                "filename": guideline_doc.filename,
                "file_url": guideline_doc.file_url,
                "size": guideline_doc.size,
                "uploaded_at": guideline_doc.uploaded_at.strftime("%d/%m/%Y %H:%M") if guideline_doc.uploaded_at else None
            }

    auditors_response = [
        {"id": qa.auditor.id, "email": qa.auditor.email}
        for qa in (q.auditors or [])
        if getattr(qa, "auditor", None)
    ]

    return {
        "message": "Questionnaire updated successfully",
        "questionnaire": {
            "id": q.id,
            "version": q.version,
            "status": q.status,
            "target_duration": str(q.target_duration) if q.target_duration else None,
            "score_calculation": q.score_calculation,
            "auditType": {
                "id": q.audit_type.id if q.audit_type else None,
                "value": q.audit_type.value if q.audit_type else None,
            } if q.audit_type else None,
            "framework": {
                "id": q.framework.id,
                "label": q.framework.label,
                "code": q.framework.code
            } if q.framework else None,
            "name": q.name,
            "auditors": auditors_response,
            "guideline": guideline_response
        }
    }


def update_questionnaire_fields_sync(
    questionnaire_id: int,
    data: dict,
    db: Session,
    force_ready_status: bool = False,
):
    q = db.query(Questionnaire).filter_by(id=questionnaire_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Questionnaire not found")
    has_updates = False

    if data.get("framework_id") and q.framework_id != data["framework_id"]:
        q.framework_id = data["framework_id"]
        has_updates = True

    if data.get("name") and q.name != data["name"]:
        q.name = data["name"]
        has_updates = True

    if data.get("target_duration"):
        current_duration = str(q.target_duration) if q.target_duration else None
        if current_duration != data["target_duration"]:
            has_updates = True
        q.target_duration = data["target_duration"]

    if data.get("status") and not force_ready_status and q.status != data["status"]:
        q.status = data["status"]
        has_updates = True

    if force_ready_status and q.status != "Ready to Use":
        q.status = "Ready to Use"
        has_updates = True

    if (
        "score_calculation" in data
        and data.get("score_calculation") is not None
        and q.score_calculation != data["score_calculation"]
    ):
        q.score_calculation = data["score_calculation"]
        has_updates = True

    if data.get("type_id"):
        audit_type = db.query(AuditType).filter_by(id=data["type_id"]).first()
        if not audit_type:
            raise HTTPException(status_code=400, detail="Invalid audit type")
        if q.type_id != audit_type.id:
            q.type_id = audit_type.id
            has_updates = True

    auditor_emails = data.get("auditor_emails")
    if auditor_emails is not None:
        existing_emails = sorted(
            {
                (qa.auditor.email or "").strip().lower()
                for qa in (q.auditors or [])
                if getattr(qa, "auditor", None) and getattr(qa.auditor, "email", None)
            }
        )
        incoming_emails = sorted({(email or "").strip().lower() for email in auditor_emails})
        if existing_emails != incoming_emails:
            has_updates = True
            db.query(QuestionnaireAuditor).filter_by(questionnaire_id=questionnaire_id).delete()

            for email in auditor_emails:
                auditor = db.query(User).filter_by(email=email).first()
                if not auditor:
                    raise HTTPException(status_code=404, detail=f"User with email {email} not found")
                db.add(
                    QuestionnaireAuditor(
                        questionnaire_id=questionnaire_id,
                        auditor_id=auditor.id,
                    )
                )

    if not q.score_calculation:
        current_framework = db.query(Framework).filter_by(id=q.framework_id).first() if q.framework_id else None
        current_type = db.query(AuditType).filter_by(id=q.type_id).first() if q.type_id else None
        q.score_calculation = infer_default_score_calculation(
            questionnaire_name=q.name,
            audit_type_value=current_type.value if current_type else None,
            framework_code=current_framework.code if current_framework else None,
            framework_label=current_framework.label if current_framework else None,
        )
        has_updates = True

    if has_updates:
        q.version = (q.version or 0) + 1

    db.commit()
    db.refresh(q)
    return q


async def update_questionnaire_with_access_control(
    questionnaire_id: int,
    data: dict,
    db: Session,
    guideline_storage: SharePointGuidelineStorage,
    guideline_file: Optional[UploadFile],
    remove_existing_guideline: bool,
    current_user_id: Optional[int],
    current_user: User,
):
    _assert_can_manage_questionnaires(current_user)
    if _requires_approval(current_user):
        q = db.query(Questionnaire).filter(Questionnaire.id == questionnaire_id).first()
        if not q:
            raise HTTPException(status_code=404, detail="Questionnaire not found")
        if q.created_by != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Auditor can only update their own Under Revision questionnaires.",
            )
        if (q.status or "").strip().lower() != "under revision":
            raise HTTPException(
                status_code=400,
                detail="Auditor can update only Under Revision questionnaires.",
            )

        data = {**data, "status": "Under Revision"}

    return await update_questionnaire_with_sharepoint(
        questionnaire_id=questionnaire_id,
        data=data,
        db=db,
        guideline_storage=guideline_storage,
        guideline_file=guideline_file,
        remove_existing_guideline=remove_existing_guideline,
        current_user_id=current_user_id,
    )

def delete_questionnaire(questionnaire_id: int, db: Session):
    q = db.query(Questionnaire).filter_by(id=questionnaire_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Questionnaire not found")
    
    # Vérifier si le questionnaire est utilisé dans des audits
    is_used = db.query(exists().where(Audit.questionnaire_id == questionnaire_id)).scalar()
    
    if is_used:
        # Si utilisé, on ne peut pas le supprimer
        raise HTTPException(
            status_code=400, 
            detail="This questionnaire cannot be deleted because it is already being used in existing audits."
        )
    
    # Si non utilisé, on peut le supprimer
    db.delete(q)
    db.commit()
    return {
        "message": "Questionnaire deleted successfully",
        "id": questionnaire_id
    }


def delete_questionnaire_with_access_control(questionnaire_id: int, db: Session, current_user: User):
    _assert_can_manage_questionnaires(current_user)
    if _requires_approval(current_user):
        q = db.query(Questionnaire).filter(Questionnaire.id == questionnaire_id).first()
        if not q:
            raise HTTPException(status_code=404, detail="Questionnaire not found")
        if q.created_by != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="Auditor can only delete their own Under Revision questionnaires.",
            )
        if (q.status or "").strip().lower() != "under revision":
            raise HTTPException(
                status_code=400,
                detail="Auditor can delete only Under Revision questionnaires.",
            )

    return delete_questionnaire(questionnaire_id, db)


def submit_questionnaire_for_approval(questionnaire_id: int, db: Session, current_user: User):
    _assert_can_manage_questionnaires(current_user)
    q = (
        db.query(Questionnaire)
        .options(
            joinedload(Questionnaire.framework),
            joinedload(Questionnaire.audit_type),
            joinedload(Questionnaire.auditors).joinedload(QuestionnaireAuditor.auditor),
            joinedload(Questionnaire.questions),
        )
        .filter(Questionnaire.id == questionnaire_id)
        .first()
    )
    if not q:
        raise HTTPException(status_code=404, detail="Questionnaire not found")

    if not _requires_approval(current_user):
        raise HTTPException(
            status_code=403,
            detail="Only auditor in approval workflow can submit for approval.",
        )
    if q.created_by != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="Auditor can submit only their own questionnaire.",
        )
    if (q.status or "").strip().lower() != "under revision":
        raise HTTPException(
            status_code=400,
            detail="Only Under Revision questionnaire can be submitted for approval.",
        )

    from app.models.checklist_change_request import ChecklistChangeRequest

    existing_pending = (
        db.query(ChecklistChangeRequest)
        .filter(
            ChecklistChangeRequest.questionnaire_id == questionnaire_id,
            ChecklistChangeRequest.entity_type == "questionnaire",
            ChecklistChangeRequest.action_type == "submit",
            ChecklistChangeRequest.status == "pending",
        )
        .first()
    )
    if existing_pending:
        return {
            "message": "This questionnaire is already submitted and pending Quality Manager review.",
            "requires_approval": True,
            "request_id": existing_pending.id,
        }

    payload = {
        "id": q.id,
        "name": q.name,
        "status": q.status,
        "version": q.version,
        "framework_id": q.framework_id,
        "framework_code": getattr(q.framework, "code", None) if q.framework else None,
        "type_id": q.type_id,
        "audit_type": getattr(q.audit_type, "value", None) if q.audit_type else None,
        "target_duration": q.target_duration,
        "auditor_emails": [
            qa.auditor.email for qa in (q.auditors or []) if getattr(qa, "auditor", None)
        ],
        "questions": [
            {
                "id": question.id,
                "description": question.description,
                "chapter": question.chapter,
                "weight": question.weight,
                "critical_value": question.critical_value,
            }
            for question in (q.questions or [])
        ],
    }

    request = submit_change_request(
        db=db,
        requested_by=current_user,
        entity_type="questionnaire",
        action_type="submit",
        questionnaire_id=questionnaire_id,
        target_id=questionnaire_id,
        payload=payload,
        request_comment="Auditor submitted questionnaire draft for approval.",
    )
    return {
        "message": "Submitted to Quality Manager for approval.",
        "requires_approval": True,
        "request_id": request.id,
    }

def get_questionnaire_id_name_list(db: Session):
    results = (
        db.query(
            Questionnaire.id,
            Questionnaire.name,
            Questionnaire.potential_analysis_questionnaire_id,
        )
        .filter(Questionnaire.status == "Ready to Use")
        .order_by(Questionnaire.name.asc())
        .all()
    )

    if not results:
        raise HTTPException(status_code=404, detail="No questionnaires found")

    return [
        {
            "id": q.id,
            "name": q.name,
            "has_potential_analysis": q.potential_analysis_questionnaire_id is not None,
        }
        for q in results
    ]
