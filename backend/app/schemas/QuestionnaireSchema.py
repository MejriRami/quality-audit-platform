from pydantic import BaseModel, EmailStr, field_serializer, field_validator
from typing import Optional, List
from datetime import datetime, time
from app.schemas.Framework import FrameworkOut
from app.schemas.auditTypeSchema import AuditTypeBase
from app.schemas.schema import QuestionOut
from app.schemas.userSchema.userSchema import UserAuditorBase

class QuestionnaireBase(BaseModel):
    framework_id: int
    name: str
    type_id: Optional[int] = None
    status : Optional[str] = None
    target_duration: Optional[time] = None
    score_calculation: Optional[str] = None
    guideline_id: Optional[int] = None
    created_by: Optional[int] = None #TODO
    auditors: Optional[List[EmailStr]] = None

class QuestionnaireCreate(BaseModel):
    name: Optional[str] = None
    target_duration: Optional[time] = None
    status: Optional[str] = None
    score_calculation: Optional[str] = None
    type_id: Optional[int] = None
    framework_id: Optional[int] = None
    auditor_emails: Optional[List[EmailStr]] = None

class QuestionnaireOut(QuestionnaireBase):
    id: int
    created_at: datetime
    questions: List[QuestionOut] = []
    framework_id: int                   
    framework: Optional[FrameworkOut] = None

    auditors: list[EmailStr] = []
    model_config = {"from_attributes": True}

class QuestionnaireResponse(BaseModel):
    id: int
    name: str
    target_duration: str
    created_by: Optional[int] = None
    version: int
    framework_id: int
    guideline_id: Optional[int] = None
    score_calculation: Optional[str] = None
    status: Optional[str]
    created_at: datetime
    type_id: int

    framework: Optional[FrameworkOut] = None
    audit_type: Optional[AuditTypeBase] = None
    auditors: Optional[List[UserAuditorBase]] = None
    questions: Optional[List[QuestionOut]] = None

    # Convert python time → string
    @field_validator("target_duration", mode="before")
    def convert_time_to_string(cls, v):
        if isinstance(v, time):
            return v.strftime("%H:%M:%S")
        return v

    class Config:
        orm_mode = True
        