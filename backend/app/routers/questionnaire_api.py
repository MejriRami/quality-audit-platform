import json
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session
from typing import  Optional
from app.config.database import get_db
from app.models.document import Document
from app.models.questionnaire import Questionnaire
from app.schemas.QuestionnaireSchema import QuestionnaireCreate
from app.services import auth_service, questionnaire_service
from app.services import checklist_change_request_service
from app.services.role_access_service import can_manage_questionnaires
import os

from app.services.sharepoint_audit_storage import SharePointAuditStorage, SharePointConfig, SharePointGuidelineStorage

router = APIRouter(
    prefix="/questionnaire", 
    tags=["Questionnaires"],
    dependencies=[Depends(auth_service.get_current_user)]
)


# Initialize SharePoint config
sp_config = SharePointConfig(
        hostname="northwindgroup.sharepoint.com",
        site_path="/sites/Northwind-internal-Audits",
    library_name="Documents",
    guidelines_root_folder="Questionnaires-guidelines"
)
sp_storage = SharePointAuditStorage(sp_config)
guideline_storage = SharePointGuidelineStorage(sp_storage)
@router.post("/add")
def create_questionnaire(
    data: QuestionnaireCreate,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    return questionnaire_service.create_questionnaire_with_access_control(data, db, current_user)


@router.get("/getAll")
def get_questionnaires(
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    return questionnaire_service.get_all_questionnaires(db, current_user)

@router.get("/names")
def get_questionnaire_id_name_list(db: Session = Depends(get_db)):
    return questionnaire_service.get_questionnaire_id_name_list(db)


@router.get("/change-requests")
def list_checklist_change_requests(
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    return checklist_change_request_service.list_change_requests(
        db=db,
        current_user=current_user,
        status=status,
    )


@router.post("/change-requests/{request_id}/approve")
def approve_checklist_change_request(
    request_id: int,
    body: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    return checklist_change_request_service.approve_change_request(
        db=db,
        request_id=request_id,
        reviewer=current_user,
        review_comment=body.get("comment"),
    )


@router.post("/change-requests/{request_id}/reject")
def reject_checklist_change_request(
    request_id: int,
    body: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    return checklist_change_request_service.reject_change_request(
        db=db,
        request_id=request_id,
        reviewer=current_user,
        review_comment=body.get("comment"),
    )



@router.get("/{questionnaire_id}")
def get_questionnaire(questionnaire_id: int, db: Session = Depends(get_db)):
    return questionnaire_service.get_questionnaire(questionnaire_id, db)

@router.put("/{questionnaire_id}")
async def update_questionnaire(
    questionnaire_id: int,
    name: Optional[str] = Form(None),
    target_duration: Optional[str] = Form(None),
    status: Optional[str] = Form(None),
    type_id: Optional[int] = Form(None),
    framework_id: Optional[int] = Form(None),
    auditor_emails: Optional[str] = Form(None),
    guideline_file: Optional[UploadFile] = File(None),
    remove_existing_guideline: Optional[bool] = Form(False),
    current_user_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    """
    Update questionnaire with optional file upload to SharePoint
    """
    # Parse auditor emails if provided
    parsed_auditor_emails = None
    if auditor_emails is not None:
        try:
            parsed_auditor_emails = json.loads(auditor_emails) if auditor_emails else []
        except json.JSONDecodeError:
            parsed_auditor_emails = [email.strip() for email in auditor_emails.split(',') if email.strip()]
    
    # Build data dictionary
    data = {}
    if name is not None:
        data['name'] = name
    if target_duration is not None:
        data['target_duration'] = target_duration
    if status is not None:
        data['status'] = status
    if type_id is not None:
        data['type_id'] = type_id
    if framework_id is not None:
        data['framework_id'] = framework_id
    if parsed_auditor_emails is not None:
        data['auditor_emails'] = parsed_auditor_emails
    
    # Call service with SharePoint storage
    return await questionnaire_service.update_questionnaire_with_access_control(
        questionnaire_id=questionnaire_id,
        data=data,
        db=db,
        guideline_storage=guideline_storage,
        guideline_file=guideline_file,  
        remove_existing_guideline=remove_existing_guideline,
        current_user_id=current_user_id,
        current_user=current_user,
    )
@router.delete("/{questionnaire_id}")
def delete_questionnaire_route(
    questionnaire_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    return questionnaire_service.delete_questionnaire_with_access_control(questionnaire_id, db, current_user)


@router.post("/{questionnaire_id}/submit-for-approval")
def submit_questionnaire_for_approval_route(
    questionnaire_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    return questionnaire_service.submit_questionnaire_for_approval(
        questionnaire_id=questionnaire_id,
        db=db,
        current_user=current_user,
    )

@router.get("/{questionnaire_id}/guideline")
async def get_questionnaire_guideline(
    questionnaire_id: int,
    download: bool = False,  # Query param: ?download=true to force download
    db: Session = Depends(get_db)
):
    """
    Get or download questionnaire guideline file
    
    Args:
        questionnaire_id: ID of the questionnaire
        download: If True, force download. If False, display in browser
    """
    # Get questionnaire
    questionnaire = db.query(Questionnaire).filter_by(id=questionnaire_id).first()
    if not questionnaire:
        raise HTTPException(status_code=404, detail="Questionnaire not found")
    
    # Check if guideline exists
    if not questionnaire.guideline_id:
        raise HTTPException(status_code=404, detail="No guideline file found for this questionnaire")
    
    # Get document
    document = db.query(Document).filter_by(id=questionnaire.guideline_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Guideline file not found")
    
    # Build file path
    file_path = os.path.join(".", document.file_url.lstrip("/"))
    
    # Check if file exists on disk
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found on server")
    
    # Determine media type and disposition
    media_type = document.mimetype or "application/octet-stream"
    
    # Set headers based on download parameter
    if download:
        # Force download
        return FileResponse(
            path=file_path,
            media_type=media_type,
            filename=document.filename,
            headers={
                "Content-Disposition": f'attachment; filename="{document.filename}"'
            }
        )
    else:
        # Display inline (for PDFs, images, etc.)
        return FileResponse(
            path=file_path,
            media_type=media_type,
            filename=document.filename,
            headers={
                "Content-Disposition": f'inline; filename="{document.filename}"'
            }
        )


@router.get("/documents/{document_id}/download")
async def download_document(
    document_id: int,
    db: Session = Depends(get_db)
):
    """
    Download document (supports both disk and SharePoint storage)
    """
    # Get document
    document = db.query(Document).filter_by(id=document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Check if file is in SharePoint
    if document.sharepoint_drive_id and document.sharepoint_item_id:
        try:
            # Download from SharePoint
            response = await sp_storage.download_content_stream(
                drive_id=document.sharepoint_drive_id,
                item_id=document.sharepoint_item_id
            )
            
            # Stream response
            async def stream_content():
                try:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        yield chunk
                finally:
                    await sp_storage.close_stream(response)
            
            return StreamingResponse(
                stream_content(),
                media_type=document.mimetype or "application/octet-stream",
                headers={
                    "Content-Disposition": f'attachment; filename="{document.filename}"'
                }
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error downloading from SharePoint: {str(e)}")
    
    # Fallback to disk storage (for legacy files)
    file_path = os.path.join(".", document.file_url.lstrip("/"))
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=file_path,
        media_type=document.mimetype or "application/octet-stream",
        filename=document.filename,
        headers={
            "Content-Disposition": f'attachment; filename="{document.filename}"'
        }
    )



@router.get("/documents/{document_id}/view")
async  def view_document(
    document_id: int,
    db: Session = Depends(get_db)
):
    """
    View document inline (supports both disk and SharePoint storage)
    Works for PDFs, images, Excel files, etc.
    """
    # Get document
    document = db.query(Document).filter_by(id=document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Check if file is in SharePoint
    if document.sharepoint_drive_id and document.sharepoint_item_id:
        try:
            # Download from SharePoint
            response = await sp_storage.download_content_stream(
                drive_id=document.sharepoint_drive_id,
                item_id=document.sharepoint_item_id
            )
            
            # Stream response
            async def stream_content():
                try:
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        yield chunk
                finally:
                    await sp_storage.close_stream(response)
            
            return StreamingResponse(
                stream_content(),
                media_type=document.mimetype or "application/octet-stream",
                headers={
                    "Content-Disposition": f'inline; filename="{document.filename}"'
                }
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error viewing from SharePoint: {str(e)}")
    
    # Fallback to disk storage (for legacy files)
    file_path = os.path.join(".", document.file_url.lstrip("/"))
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=file_path,
        media_type=document.mimetype or "application/octet-stream",
        filename=document.filename,
        headers={
            "Content-Disposition": f'inline; filename="{document.filename}"'
        }
    )

@router.delete("/documents/{questionnaire_id}/guideline")
async def delete_questionnaire_guideline(
    questionnaire_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(auth_service.get_current_user),
):
    """
    Delete questionnaire guideline from SharePoint and database
    """
    if not can_manage_questionnaires(current_user):
        raise HTTPException(
            status_code=403,
            detail="You are not allowed to delete questionnaire guidelines.",
        )

    # Get questionnaire
    q = db.query(Questionnaire).filter_by(id=questionnaire_id).first()
    if not q:
        raise HTTPException(status_code=404, detail="Questionnaire not found")
    
    if not q.guideline_id:
        raise HTTPException(status_code=404, detail="No guideline found for this questionnaire")
    
    # Get document
    document = db.query(Document).filter_by(id=q.guideline_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Guideline document not found")
    
    try:
        # Delete from SharePoint if it's stored there
        if document.sharepoint_drive_id and document.sharepoint_item_id:
            await guideline_storage.delete_guideline(
                drive_id=document.sharepoint_drive_id,
                item_id=document.sharepoint_item_id
            )
        else:
            # Delete from disk (legacy files)
            file_path = os.path.join(".", document.file_url.lstrip("/"))
            if os.path.exists(file_path):
                os.remove(file_path)
        
        # Delete from database
        db.delete(document)
        q.guideline_id = None
        db.commit()
        
        return {"message": "Guideline deleted successfully"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting guideline: {str(e)}")
