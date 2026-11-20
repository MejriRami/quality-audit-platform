from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.audit_type import AuditType
from app.models.questionnaire import Questionnaire


def create_audit_type(db: Session, value: str):
    value = value.strip().lower()
    existing = db.query(AuditType).filter(AuditType.value == value).first()
    if existing:
        return existing 
    new_type = AuditType(value=value)
    db.add(new_type)
    db.commit()
    db.refresh(new_type)
    return new_type

def get_all_audit_types(db: Session):
    return db.query(AuditType).all()

def delete_audit_type(audit_type_id: int, db: Session):
    f = db.query(AuditType).filter_by(id=audit_type_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="Audit type not found")
    used = db.query(Questionnaire).filter(Questionnaire.type_id == audit_type_id).first()
    if used:
        raise HTTPException(
            status_code=400,
            detail="Impossible de supprimer ce type : il est utilisé par au moins un questionnaire."
        )

    db.delete(f)
    db.commit()
    return {
        'message': 'Audit type deleted successfully',
        'id': audit_type_id
    }