# app/api/files.py
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services.blob_storage_service import upload_misc_document

router = APIRouter(prefix="/files", tags=["files"])

@router.post("/upload", summary="Upload file -> returns file_url + metadata (no DB insert)")
async def upload_file(
    file: UploadFile = File(...),
    _: User = Depends(get_current_user),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Invalid file name")
    upload = await upload_misc_document(file=file, purpose="draft")

    return {
        "filename": upload["filename"],
        "mimetype": upload["mimetype"],
        "size": upload["size"],
        "file_url": upload["file_url"],
    }

# @router.post("/upload", summary="Upload file -> returns document_id + file_url")
# async def upload_file(
    # file: UploadFile = File(...),
    # db: Session = Depends(get_db),
    # user_id: int = Depends(get_current_user_id),  # TODO if you have auth
# ):
    # ensure folder exists
    # UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # if not file.filename:
    #     raise HTTPException(status_code=400, detail="Invalid file name")

    # #  sanitize filename + generate unique file name
    # original_name = Path(file.filename).name
    # ext = Path(original_name).suffix
    # saved_name = f"{uuid4().hex}{ext}"
    # saved_path = UPLOAD_DIR / saved_name

    # # save file to disk (stream)
    # try:
    #     with saved_path.open("wb") as buffer:
    #         shutil.copyfileobj(file.file, buffer)
    # finally:
    #     file.file.close()

    # # read file size after write
    # size = saved_path.stat().st_size

    # # store in DB
    # doc = Document(
    #     filename=original_name,
    #     mimetype=file.content_type or "application/octet-stream",
    #     size=size,
    #     file_url=f"/uploads/{saved_name}",  
    #     uploaded_at=datetime.utcnow(),
    #     # uploaded_by=user_id,  # TODO enable when auth exists
    # )
    # db.add(doc)
    # db.commit()
    # db.refresh(doc)

    # return {
    #     "document_id": doc.id,
    #     "filename": doc.filename,
    #     "mimetype": doc.mimetype,
    #     "size": doc.size,
    #     "file_url": doc.file_url,
    # }
