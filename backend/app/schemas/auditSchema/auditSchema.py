from pydantic import BaseModel, EmailStr, field_validator, Field
from datetime import datetime, date, time
from typing import List, Optional


class auditeeAvailability(BaseModel):
    auditee_emails: List[EmailStr]
    audit_date: date
    start_time: time
    end_time: time


class AuditeeInput(BaseModel):
    """One auditee entry from the Northwind directory picker. `people_id` is set
    when the auditee was picked from the directory, left None for a
    manually-typed email (most Northwind staff don't have an email in the
    directory - see app/services/org_member_directory.py)."""

    email: EmailStr
    people_id: Optional[int] = None


class AuditeeOut(BaseModel):
    """Response-side mirror of AuditeeInput - lets the frontend know which
    already-assigned auditees came from the directory (so re-opening a
    picker doesn't show them as "manual" just because the response only
    carried plain emails). Additive alongside the existing plain-string
    `auditees`/`auditee_emails` fields, never replacing them."""

    email: str
    people_id: Optional[int] = None


class AuditPlanCreate(BaseModel):
    auditee_emails: list[EmailStr]
    # Optional, richer alternative to auditee_emails - when present and
    # non-empty, takes priority (see audit_service.resolve_auditee_inputs).
    # Kept separate rather than replacing auditee_emails so existing
    # clients that only send plain emails keep working unchanged.
    auditees: Optional[List[AuditeeInput]] = None
    auditor_id: int
    second_auditor_id: Optional[int] = None
    plant: str
    sector: Optional[str] = None
    questionnaire_id: int
    supervisor_email: Optional[EmailStr] = None
    hardware_email: Optional[str] = None
    audit_date: date
    start_time: time
    end_time: time
    allow_unavailable_auditee: bool = False


class UserMini(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str

    class Config:
        from_attributes = True


class QuestionnaireMini(BaseModel):
    name: str
    type: Optional[str] = None

    class Config:
        from_attributes = True


class AuditPlanningDetailsUpdate(BaseModel):
    auditee_emails: list[EmailStr]
    auditees: Optional[List[AuditeeInput]] = None
    plant: str
    sector: Optional[str] = None
    supervisor_email: Optional[EmailStr] = None
    hardware_email: Optional[str] = None
    audit_date: date
    start_time: time
    end_time: time


class AuditPlanningDetailsResponse(BaseModel):
    audit_id: int
    audit_number: Optional[str] = None
    status: str
    event_created: bool = False
    event_id: Optional[str] = None
    calendar_sync_needed: Optional[bool] = None
    plant: Optional[str] = None
    sector: Optional[str] = None
    supervisor_email: Optional[EmailStr] = None
    hardware_email: Optional[str] = None
    audit_date: date
    start_time: time
    end_time: time
    auditee_emails: list[EmailStr]
    auditee_details: List[AuditeeOut] = []
    auditor: Optional[UserMini] = None
    second_auditor: Optional[UserMini] = None
    questionnaire_id: Optional[int] = None
    questionnaire: Optional[QuestionnaireMini] = None

    class Config:
        from_attributes = True


class AuditPlanningSyncResponse(BaseModel):
    ok: bool
    audit_id: int
    event_action: str
    event_created: bool
    event_id: Optional[str] = None


class AuditResponse(BaseModel):
    id: int
    audit_number: Optional[str] = None
    status: str
    planned_start_date: datetime
    planned_end_date: datetime
    plant: Optional[str] = None
    sector: Optional[str] = None

    # FIXED HERE
    total_score: Optional[float] = None

    supervisor_email: Optional[EmailStr] = None
    event_created: Optional[bool] = None

    auditor: Optional[UserMini] = None
    second_auditor: Optional[UserMini] = None
    auditees: list[str]
    auditee_details: List[AuditeeOut] = []
    questionnaire: Optional[QuestionnaireMini] = None

    actual_start_date: Optional[datetime] = None
    actual_end_date: Optional[datetime] = None

    weak_points: Optional[str] = None
    strong_points: Optional[str] = None
    cancel_reason: Optional[str] = None

    report_exists: bool = False

    class Config:
        from_attributes = True
        json_encoders = {datetime: lambda v: v.strftime("%Y-%m-%d %H:%M")}


class AuditListResponse(BaseModel):
    audits: list[AuditResponse]


class AuditRescheduleRequest(BaseModel):
    new_start_date: datetime
    new_end_date: datetime
    reason: str
    email: EmailStr
    allow_unavailable_auditee: bool = False


class AuditCancelRequest(BaseModel):
    reason_code: int
    reason: Optional[str] = None
    email: EmailStr


class AuditAuditeeUpdateRequest(BaseModel):
    auditee_emails: List[EmailStr]
    auditees: Optional[List[AuditeeInput]] = None
    email: EmailStr
    allow_unavailable_auditee: bool = False


class AuditRescheduleHistoryResponse(BaseModel):
    id: int
    action_type: str
    old_date: Optional[datetime]
    new_date: Optional[datetime]
    reason_code: Optional[int] = None
    reason: Optional[str]
    changed_by: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AuditAuditorResponse(BaseModel):
    id: int
    audit_number: Optional[str]
    status: str
    planned_start_date: datetime
    planned_end_date: datetime
    plant: Optional[str] = None
    sector: Optional[str] = None
    event_created: Optional[bool]
    auditor_id: int
    auditees: list[str]
    auditee_details: List[AuditeeOut] = []
    auditor: UserMini

    audit_type: Optional[str] = None
    framework_code: Optional[str] = None
    framework_label: Optional[str] = None

    total_score: Optional[float] = None

    report_url: Optional[str] = None

    @field_validator("auditees", mode="before")
    def extract_emails(cls, auditees):
        if auditees is None:
            return []

        normalized: list[str] = []

        for a in auditees:
            if isinstance(a, str):
                normalized.append(a)

            elif isinstance(a, dict):
                email = a.get("email") or a.get("auditee_email")

                if email:
                    normalized.append(str(email))

            else:
                email = getattr(a, "email", None) or getattr(a, "auditee_email", None)

                if email:
                    normalized.append(str(email))

        return normalized

    class Config:
        from_attributes = True


class PaginatedAuditResponse(BaseModel):
    items: List[AuditAuditorResponse]
    page: int
    per_page: int
    total: int
    total_pages: int

    class Config:
        from_attributes = True


class QuestionResponse(BaseModel):
    id: int
    description: str
    critical_value: int
    weight: Optional[int] = None

    class Config:
        from_attributes = True


class DocumentCreate(BaseModel):
    filename: str
    mimetype: str
    size: int
    file_url: str


class AuditAnswerCreate(BaseModel):
    class RequirementAnswerCreate(BaseModel):
        question_requirement_id: int
        value: Optional[int] = None
        fulfilled: Optional[bool] = None
        finding_text: Optional[str] = None
        evidence: List[DocumentCreate] = Field(default_factory=list)

    question_id: int
    value: int
    identifier: Optional[str] = None
    finding_text: Optional[str] = None

    documents: List[DocumentCreate] = Field(default_factory=list)

    car_reason: Optional[str] = None
    request_car: bool = False
    immediate_action_required: bool = False
    silent_box: bool = False

    critical_value: int

    process: Optional[str] = None
    standard_paragraph: Optional[str] = None
    classification: Optional[str] = None
    question_text: Optional[str] = None
    auditee_id: Optional[int] = None

    requirements: List[RequirementAnswerCreate] = Field(default_factory=list)


class ExecuteAuditRequest(BaseModel):
    answers: List[AuditAnswerCreate]
    audit_date: str
    start_time: str
    end_time: str
    strong_points: Optional[str] = None
    weak_points: Optional[str] = None


class AuditeeMini(BaseModel):
    id: int
    email: Optional[str] = None

    class Config:
        from_attributes = True


class AuditPickerItem(BaseModel):
    id: int
    audit_number: str
    planned_date: str
    planned_start_time: str
    planned_end_time: str
    status: str

    auditees: List[AuditeeMini] = []

    questionnaire_name: Optional[str] = None
    plant: Optional[str] = None

    framework_code: Optional[str] = None
    framework_label: Optional[str] = None
    audit_type_value: Optional[str] = None
    score_calculation: Optional[str] = None

    class Config:
        from_attributes = True


class AddUnavailabilityInput(BaseModel):
    token: str
    start_date: date
    end_date: date
    reason: str | None = None


class AuditDraftRequest(BaseModel):
    """
    All fields are optional – the client sends only what it has so far.
    Nothing is validated for completeness; that happens on /execute.
    """

    audit_date: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None

    strong_points: Optional[str] = None
    weak_points: Optional[str] = None

    answers: Optional[List["AuditDraftAnswer"]] = None

    expected_draft_etag: Optional[str] = None


class AuditDraftAnswer(BaseModel):
    question_id: Optional[int] = None
    draft_row_id: Optional[str] = None

    value: Optional[int] = None

    finding_text: Optional[str] = None

    request_car: Optional[bool] = None
    car_reason: Optional[str] = None
    silent_box: Optional[bool] = None

    documents: List[DocumentCreate] = Field(default_factory=list)

    process: Optional[str] = None
    standard_paragraph: Optional[str] = None
    classification: Optional[str] = None
    question_text: Optional[str] = None


class AuditDraftResponse(BaseModel):
    audit_id: int
    saved_at: Optional[datetime] = None

    audit_date: Optional[str]
    start_time: Optional[str]
    end_time: Optional[str]

    strong_points: Optional[str]
    weak_points: Optional[str]

    answers: Optional[List[AuditDraftAnswer]] = None

    draft_etag: Optional[str] = None

    class Config:
        from_attributes = True
