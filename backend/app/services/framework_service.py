from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models.framework import Framework
from app.schemas.schema import FrameworkCreate,FrameworkUpdate

def create_framework(data:FrameworkCreate, db: Session):
    existing = db.query(Framework).filter_by(code=data.code).first()
    if existing:
        raise HTTPException(status_code=400, detail="Framework code already exists")
    framework = Framework(code=data.code, label=data.label)
    db.add(framework)
    db.commit()
    db.refresh(framework)
    return framework

def update_framework(framework_id: int, data: FrameworkUpdate, db: Session):
    framework = db.query(Framework).filter_by(id=framework_id).first()
    if not framework:
        raise HTTPException(status_code=404, detail="Framework not found")
    if data.label:
        framework.label = data.label
    if data.code:
        framework.code = data.code
    db.commit()
    db.refresh(framework)
    return framework

def get_all_frameworks(db: Session):
    frameworks = db.query(Framework).order_by(Framework.id.asc()).all()
    if not frameworks:
        raise HTTPException(status_code=404, detail="No frameworks found")
    return frameworks

def get_framework(framework_id: int, db: Session):
    f = db.query(Framework).filter_by(id=framework_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="Framework not found")
    return f

def delete_framework(framework_id: int, db: Session):
    framework = db.query(Framework).filter_by(id=framework_id).first()
    if not framework:
        raise HTTPException(status_code=404, detail="Framework not found")
    db.delete(framework)
    db.commit()
    return {
        "message": "Framework deleted successfully",
        "id": framework_id
    }