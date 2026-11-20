from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.config.database import get_db
from app.schemas.auditTypeSchema import AuditTypeCreate, AuditTypeBase
from app.services.audit_type_service import create_audit_type, get_all_audit_types, delete_audit_type

router = APIRouter(prefix="/audit-types", tags=["Audit Types"])


# GET all audit types
@router.get("/all", response_model=List[AuditTypeBase])
def read_audit_types(db: Session = Depends(get_db)):
    return get_all_audit_types(db)

# POST create a new audit type
@router.post("/add", response_model=AuditTypeBase)
def create_new_audit_type(payload: AuditTypeCreate, db: Session = Depends(get_db)):
    new_type = create_audit_type(db, payload.value)
    return new_type

@router.delete("/{audit_type_id}", response_model=dict)
def delete_type(audit_type_id: int, db: Session = Depends(get_db)):
    return delete_audit_type(audit_type_id, db)
