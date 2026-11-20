from pydantic import BaseModel
from typing import List, Optional
from pydantic import BaseModel

from app.routers.car_admin import DocumentItem


class QuestionOut(BaseModel):
    id: int
    description: str
    chapter: Optional[str] = None
    weight: Optional[int] = None
    critical_value: Optional[int] = None
    question_code: Optional[str] = None
    element: Optional[str] = None
    subgroup: Optional[str] = None
    is_asterisk: Optional[bool] = None
 
    class Config:
        from_attributes = True
 
 
class AuditAnswerOut(BaseModel):
    id: int
    identifier: Optional[str] = None
    value: int
    finding_text: Optional[str] = None
    fail: Optional[bool] = None
    improve: Optional[bool] = None
    pass_: Optional[bool] = None
    process: Optional[str] = None
    standard_paragraph: Optional[str] = None
    classification: Optional[str] = None
    question_text: Optional[str] = None
    silent_box: Optional[bool] = None
    created_at: Optional[str] = None
    # Joined question (None for IATF NC direct answers)
    question: Optional[QuestionOut] = None
    documents: List[DocumentItem] = []
 
    class Config:
        from_attributes = True
 
 
class AuditAnswersResponse(BaseModel):
    audit_id: int
    audit_number: str
    total_answers: int
    total_pass: int
    total_improve: int
    total_fail: int
    items: List[AuditAnswerOut]
