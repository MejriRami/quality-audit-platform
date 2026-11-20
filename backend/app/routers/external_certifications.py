"""External certifications (ported from the standalone certification_crud_app).

Two ways in: an app login (Bearer token), or the public certifications
portal (X-Certification-Session, from an emailed code - see
certification_portal_service).

Read access: everyone signed in either way.
Write access: admin, quality managers, auditors, certification_editor, and
Northwind directory quality managers / quality engineers / group quality."""

from datetime import date, datetime
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.services import certification_expiry_service as expiry
from app.services import certification_portal_service as portal
from app.services import external_certification_service as service
from app.services.auth_service import verify_token
from app.services.certification_portal_service import CertificationActor

router = APIRouter(prefix="/external-certifications", tags=["External Certifications"])


def certification_viewer(
    authorization: Optional[str] = Header(None),
    x_certification_session: Optional[str] = Header(None, alias="X-Certification-Session"),
    db: Session = Depends(get_db),
) -> CertificationActor:
    if x_certification_session:
        return portal.actor_from_session(db, x_certification_session)
    scheme, _, token = (authorization or "").partition(" ")
    user = verify_token(token, db) if scheme.lower() == "bearer" and token else None
    if not user:
        raise HTTPException(status_code=401, detail="Please sign in to view certifications.")
    return portal.actor_for_user(db, user)


def certification_editor(actor: CertificationActor = Depends(certification_viewer)) -> CertificationActor:
    if not actor.can_edit:
        raise HTTPException(status_code=403, detail="You can view certifications but not modify them.")
    return actor


# ─────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────


class CertificationStatus(str, Enum):
    pending_review = "pending_review"
    validated = "validated"
    rejected = "rejected"
    expired = "expired"


class AuditGroup(str, Enum):
    certification_review = "certification_review"
    certification_audits_2025 = "certification_audits_2025"
    validated_certification_after_review = "validated_certification_after_review"
    internal_audit = "internal_audit"
    customer_cross_site_audit = "customer_cross_site_audit"
    external_audit = "external_audit"


class DocumentType(str, Enum):
    certificate = "certificate"
    report = "report"
    # The NcManagement .json export of the IATF CARA platform.
    report_json_iatf_cara = "report.json for IATF CARA"
    other = "other"


class CertificationBase(BaseModel):
    certification_number: Optional[str] = None
    name: str
    certification_type: Optional[str] = None
    document_type: Optional[DocumentType] = None
    # Shown as "Certificate Scope" when document_type is certificate.
    scope: Optional[str] = None
    plant: Optional[str] = None
    quality_manager_name: Optional[str] = None
    quality_manager_email: Optional[str] = None
    external_certification_body: Optional[str] = None
    audit_date: Optional[date] = None
    date_of_last_audit: Optional[date] = None
    next_expected_audit: Optional[date] = None
    certification_expiration_date: Optional[date] = None
    status: CertificationStatus = CertificationStatus.pending_review
    rejected_reason: Optional[str] = None
    automation_status: Optional[str] = None
    quality_manager_decision: Optional[str] = None
    monday_group: Optional[AuditGroup] = None

    @field_validator("quality_manager_email")
    @classmethod
    def blank_email_to_none(cls, v):
        if v is not None and v.strip() == "":
            return None
        return v


class CertificationIn(CertificationBase):
    pass


class CertificationOut(CertificationBase):
    id: int
    monday_item_id: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    nonconformity_count: int = 0
    document_count: int = 0


class MetaOut(BaseModel):
    statuses: list[str]
    document_types: list[str] = [t.value for t in DocumentType]
    monday_groups: list[str]
    plants: list[str]
    certification_types: list[str]


class DocumentOut(BaseModel):
    id: int
    document_type: Optional[str] = None
    filename: Optional[str] = None
    uploaded_at: Optional[datetime] = None
    download_url: str


def _payload(data: CertificationIn) -> dict:
    return {k: (v.value if isinstance(v, Enum) else v) for k, v in data.model_dump().items()}


# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────


@router.get("/meta", response_model=MetaOut)
def get_meta(_: CertificationActor = Depends(certification_viewer)):
    return service.get_meta()


@router.get("", response_model=list[CertificationOut])
def list_certifications(
    search: Optional[str] = Query(None, description="Matches name, certification_number, or plant"),
    status: Optional[str] = None,
    plant: Optional[str] = None,
    monday_group: Optional[str] = None,
    _: CertificationActor = Depends(certification_viewer),
):
    return service.list_certifications(search=search, status=status, plant=plant, monday_group=monday_group)


class PortalCodeRequest(BaseModel):
    email: str


class PortalCodeVerify(BaseModel):
    email: str
    code: str


@router.post("/portal/request-code")
def portal_request_code(data: PortalCodeRequest, db: Session = Depends(get_db)):
    """Public: emails a one-time code to an @northwind.com address."""
    return portal.request_code(db, data.email)


@router.post("/portal/verify-code")
def portal_verify_code(data: PortalCodeVerify, db: Session = Depends(get_db)):
    """Public: exchanges the code for a portal session token."""
    return portal.verify_code(db, data.email, data.code)


@router.get("/me")
def get_me(actor: CertificationActor = Depends(certification_viewer)):
    return {"email": actor.email, "can_edit": actor.can_edit}


@router.post("/expiry-notifications")
def run_expiry_notifications(dry_run: bool = True, _: CertificationActor = Depends(certification_editor)):
    """Lists (dry_run, the default) or sends the "certificate expired" emails
    for certificates not yet notified. Sending works even while the daily job
    is disabled, so the first batch can be checked and sent by hand."""
    return {
        "daily_job_enabled": expiry.emails_enabled(),
        "certificates": expiry.notify_expired_certificates(dry_run=dry_run),
    }


@router.get("/{cert_id}", response_model=CertificationOut)
def get_certification(cert_id: int, _: CertificationActor = Depends(certification_viewer)):
    return service.get_certification(cert_id)


@router.post("", response_model=CertificationOut, status_code=201)
def create_certification(payload: CertificationIn, _: CertificationActor = Depends(certification_editor)):
    return service.create_certification(_payload(payload))


@router.put("/{cert_id}", response_model=CertificationOut)
def update_certification(cert_id: int, payload: CertificationIn, _: CertificationActor = Depends(certification_editor)):
    return service.update_certification(cert_id, _payload(payload))


@router.delete("/{cert_id}", status_code=204)
def delete_certification(cert_id: int, _: CertificationActor = Depends(certification_editor)):
    service.delete_certification(cert_id)


@router.get("/{cert_id}/documents", response_model=list[DocumentOut])
def list_documents(cert_id: int, _: CertificationActor = Depends(certification_viewer)):
    return service.list_documents(cert_id)


@router.post("/{cert_id}/documents", response_model=DocumentOut, status_code=201)
async def upload_document(
    cert_id: int,
    file: UploadFile = File(...),
    document_type: Optional[str] = Form(None),
    _: CertificationActor = Depends(certification_editor),
):
    data = await file.read()
    return await run_in_threadpool(
        service.upload_document, cert_id, data, file.filename, file.content_type, document_type
    )


@router.delete("/{cert_id}/documents/{doc_id}", status_code=204)
def delete_document(cert_id: int, doc_id: int, _: CertificationActor = Depends(certification_editor)):
    service.delete_document(cert_id, doc_id)
