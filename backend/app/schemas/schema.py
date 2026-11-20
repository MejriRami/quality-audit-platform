from pydantic import BaseModel, EmailStr
from datetime import datetime, date
from typing import Optional, List
from datetime import time
import uuid
from app.schemas.enum import AuditStatusEnum, PlantEnum, AuditActionEnum, CAStatusEnum, CADecisionEnum



# =====================================================
# SCHEMAS
# =====================================================
class FrameworkBase(BaseModel):
    code: str
    label: str

class FrameworkCreate(FrameworkBase):
    pass

class FrameworkUpdate(BaseModel):
    code : Optional [str] = None
    label : Optional [str]= None

class FrameworkOut(BaseModel):
    id: int
    code: str
    label: str

    model_config = {"from_attributes": True}


class QuestionBase(BaseModel):
    description: str

    chapter: Optional[str] = None
    weight: Optional[int] = None
    critical_value: Optional[int] = None
    question_code: Optional[str] = None
    element: Optional[str] = None
    subgroup: Optional[str] = None
    is_asterisk: Optional[bool] = None

class QuestionCreate(QuestionBase):
    pass

class QuestionUpdate(BaseModel):
    description: Optional[str] = None
    chapter: Optional[str] = None
    weight: Optional[int] = None
    critical_value: Optional[int] = None
    question_code: Optional[str] = None
    element: Optional[str] = None
    subgroup: Optional[str] = None
    is_asterisk: Optional[bool] = None

class QuestionOut(QuestionBase):
    id: int

    model_config = {"from_attributes": True}

from datetime import time



class QuestionSchema(BaseModel):
    id: int
    description: str
    chapter: Optional[str] = None
    weight: Optional[int] = None
    critical_value: Optional[int] = None
    question_code: Optional[str] = None
    element: Optional[str] = None
    subgroup: Optional[str] = None
    is_asterisk: Optional[bool] = None

    model_config = {"from_attributes": True}


class AuditBase(BaseModel):
    status: AuditStatusEnum = AuditStatusEnum.planned

    planned_start_date: datetime
    planned_end_date: datetime
    actual_start_date: Optional[datetime]
    actual_end_date: Optional[datetime]

    plant: Optional[PlantEnum]
    sector: Optional[str]

    auditor_id: int
    auditee_id: int
    questionnaire_id: int

    report_url: Optional[str]
    hardware_email: Optional[str]

    total_score: Optional[float]
    weak_points: Optional[str]
    strong_points: Optional[str]

class AuditCreate(AuditBase):
    pass

# Pydantic schema

class AuditUpdate(BaseModel):
    status: Optional[AuditStatusEnum]
    actual_start_date: Optional[datetime]
    actual_end_date: Optional[datetime]
    report_url: Optional[str]
    total_score: Optional[float]
    weak_points: Optional[str]
    strong_points: Optional[str]
class AuditOut(AuditBase):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}
class AuditRescheduleHistoryBase(BaseModel):
    audit_id: int
    action_type: AuditActionEnum
    old_date: Optional[datetime]
    new_date: Optional[datetime]
    reason: Optional[str]
    changed_by: Optional[int]

class AuditRescheduleHistoryCreate(AuditRescheduleHistoryBase):
    pass

class AuditRescheduleHistoryOut(AuditRescheduleHistoryBase):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}
class EvidenceBase(BaseModel):
    file_url: Optional[str]

class EvidenceCreate(EvidenceBase):
    audit_answer_id: int

class EvidenceOut(EvidenceBase):
    id: int

    model_config = {"from_attributes": True}
class AuditAnswerBase(BaseModel):
    audit_id: int
    question_id: int
    value: int
    finding_text: Optional[str]
    fail: Optional[bool]
    improve: Optional[bool]
    pass_: Optional[bool]

class AuditAnswerCreate(AuditAnswerBase):
    pass

class AuditAnswerOut(AuditAnswerBase):
    id: int
    created_at: datetime
    evidence_files: List[EvidenceOut] = []

    model_config = {"from_attributes": True}
class CorrectiveActionBase(BaseModel):
    audit_id: int
    audit_answer_id: int
    auditee_id: int
    pilot_user_id: int
    reason_why: Optional[str]
    due_date: Optional[date]
    status: CAStatusEnum = CAStatusEnum.pending
    escalated: bool = False
class CorrectiveActionCreate(CorrectiveActionBase):
    pass

class CorrectiveActionUpdate(BaseModel):
    reason_why: Optional[str]
    due_date: Optional[date]
    status: Optional[CAStatusEnum]
    escalated: Optional[bool]
class CorrectiveActionOut(CorrectiveActionBase):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}
class CorrectiveActionFileBase(BaseModel):
    file_url: Optional[str]
    implemented_solution: Optional[str]
    uploaded_by: Optional[int]

class CorrectiveActionFileCreate(CorrectiveActionFileBase):
    corrective_action_id: int

class CorrectiveActionFileOut(CorrectiveActionFileBase):
    id: int
    uploaded_at: datetime

    model_config = {"from_attributes": True}
class CAEscalationBase(BaseModel):
    email_sent_to: int
    comment: Optional[str]

class CAEscalationCreate(CAEscalationBase):
    corrective_action_id: int

class CAEscalationOut(CAEscalationBase):
    id: int
    escalated_at: datetime

    model_config = {"from_attributes": True}
class CorrectiveActionHistoryBase(BaseModel):
    corrective_action_id: int
    auditor_id: int
    decision: CADecisionEnum
    comment: Optional[str]

class CorrectiveActionHistoryCreate(CorrectiveActionHistoryBase):
    pass

class CorrectiveActionHistoryOut(CorrectiveActionHistoryBase):
    id: int
    reviewed_at: datetime

    model_config = {"from_attributes": True}
