"""
car_router.py
=============
HTTP layer for Corrective Action Reports (CAR).

All business logic lives in app.services.car_service.
This module only handles:
  - Route declaration
  - HTTP input parsing / validation
  - Calling the appropriate service function
  - Returning the result
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Response, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.models.corrective_action import CorrectiveAction
from app.schemas.auditSchema.auditSchema import AddUnavailabilityInput
from app.services import car_service
from app.services import chatbot_service
from app.utils.due_date import get_remaining_working_days

router = APIRouter(prefix="/car", tags=["cars"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schemas (HTTP-level only)
# ---------------------------------------------------------------------------

class RequestOTPInput(BaseModel):
    token: str
    email: EmailStr


class VerifyOTPInput(BaseModel):
    token: str
    email: EmailStr
    code: str


class PortalRequestOTPInput(BaseModel):
    plant: str
    email: EmailStr
    access_mode: str = "auditee"


class PortalVerifyOTPInput(BaseModel):
    plant: str
    email: EmailStr
    access_mode: str = "auditee"
    code: str


class ReassignCarInput(BaseModel):
    token: str
    email: EmailStr
    new_email: EmailStr
    reason: Optional[str] = None
    portal_session_token: Optional[str] = None
    portal_plant: Optional[str] = None
    portal_access_mode: str = "auditee"


class AddCcInput(BaseModel):
    token: str
    email: EmailStr
    cc_emails: List[EmailStr]
    portal_session_token: Optional[str] = None
    portal_plant: Optional[str] = None
    portal_access_mode: str = "auditee"


# ---------------------------------------------------------------------------
# Step 1 – Request OTP
# ---------------------------------------------------------------------------

@router.post("/request-otp")
async def request_email_otp(
    data: RequestOTPInput,
    db: Session = Depends(get_db),
):
    """
    User provides email + token.
    Returns already_submitted=True when the form is locked, otherwise sends OTP.
    """
    return await car_service.request_otp(
        token=data.token,
        email=data.email,
        db=db,
    )


# ---------------------------------------------------------------------------
# Step 2 – Verify OTP
# ---------------------------------------------------------------------------

@router.post("/verify-otp")
async def verify_email_otp(
    data: VerifyOTPInput,
    db: Session = Depends(get_db),
):
    """Validate the 6-digit OTP code the user received by email."""
    return car_service.verify_otp(
        token=data.token,
        email=data.email,
        code=data.code,
        db=db,
    )


@router.get("/portal/plants")
def get_auditee_portal_plants(
    db: Session = Depends(get_db),
):
    return {"plants": car_service.get_auditee_portal_plants(db)}


@router.post("/portal/request-otp")
async def request_auditee_portal_otp(
    data: PortalRequestOTPInput,
    db: Session = Depends(get_db),
):
    return await car_service.request_auditee_portal_otp(
        plant=data.plant,
        email=data.email,
        access_mode=data.access_mode,
        db=db,
    )


@router.post("/portal/verify-otp")
async def verify_auditee_portal_otp(
    data: PortalVerifyOTPInput,
    db: Session = Depends(get_db),
):
    return car_service.verify_auditee_portal_otp(
        plant=data.plant,
        email=data.email,
        access_mode=data.access_mode,
        code=data.code,
        db=db,
    )


@router.get("/portal/audits")
def get_auditee_portal_audits(
    plant: str,
    email: str,
    access_mode: str = Query("auditee"),
    status: Optional[str] = Query(None),
    x_portal_session: str = Header(..., alias="X-Portal-Session"),
    db: Session = Depends(get_db),
):
    return car_service.get_auditee_portal_data(
        plant=plant,
        email=email,
        access_mode=access_mode,
        session_token=x_portal_session,
        db=db,
        status=status,
    )


# ---------------------------------------------------------------------------
# Step 3 – Get form data
# ---------------------------------------------------------------------------

@router.get("/form")
async def get_car_form(
    token: str,
    email: str,
    portal_session_token: str | None = None,
    portal_plant: str | None = None,
    portal_access_mode: str = "auditee",
    db: Session = Depends(get_db),
        response: Response = None,

):
    """
    Return CAR display data including any pre-filled implemented_solution,
    root_cause, and already-uploaded documents.
    OTP must be verified first.
    """
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return car_service.get_car_form_data(
        token=token,
        email=email,
        db=db,
        portal_session_token=portal_session_token,
        portal_plant=portal_plant,
        portal_access_mode=portal_access_mode,
    )
# ---------------------------------------------------------------------------
# AI chatbot coach
# ---------------------------------------------------------------------------

class ChatMessageInput(BaseModel):
    plant: str
    email: EmailStr
    access_mode: str = "auditee"
    message: str
    car_id: Optional[int] = None


@router.get("/portal/chatbot/history")
def get_chatbot_history(
    plant: str,
    email: str,
    access_mode: str = Query("auditee"),
    x_portal_session: str = Header(..., alias="X-Portal-Session"),
    db: Session = Depends(get_db),
):
    return chatbot_service.get_chat_history(
        plant=plant,
        email=email,
        access_mode=access_mode,
        session_token=x_portal_session,
        db=db,
    )


@router.post("/portal/chatbot/message")
def post_chatbot_message(
    data: ChatMessageInput,
    x_portal_session: str = Header(..., alias="X-Portal-Session"),
    db: Session = Depends(get_db),
):
    return chatbot_service.send_message(
        plant=data.plant,
        email=data.email,
        access_mode=data.access_mode,
        session_token=x_portal_session,
        db=db,
        message=data.message,
        car_id=data.car_id,
    )


class ChatDraftInput(BaseModel):
    plant: str
    email: EmailStr
    access_mode: str = "auditee"
    car_id: int


@router.post("/portal/chatbot/draft")
def post_chatbot_draft(
    data: ChatDraftInput,
    x_portal_session: str = Header(..., alias="X-Portal-Session"),
    db: Session = Depends(get_db),
):
    return chatbot_service.generate_draft(
        plant=data.plant,
        email=data.email,
        access_mode=data.access_mode,
        session_token=x_portal_session,
        db=db,
        car_id=data.car_id,
    )


@router.post("/portal/chatbot/document")
async def post_chatbot_document(
    plant: str = Form(...),
    email: str = Form(...),
    access_mode: str = Form("auditee"),
    car_id: int = Form(...),
    file: UploadFile = File(...),
    x_portal_session: str = Header(..., alias="X-Portal-Session"),
    db: Session = Depends(get_db),
):
    return await chatbot_service.upload_document(
        plant=plant,
        email=email,
        access_mode=access_mode,
        session_token=x_portal_session,
        db=db,
        file=file,
        car_id=car_id,
    )


@router.get("/portal/chatbot/documents")
def get_chatbot_documents(
    plant: str,
    email: str,
    car_id: int,
    access_mode: str = Query("auditee"),
    x_portal_session: str = Header(..., alias="X-Portal-Session"),
    db: Session = Depends(get_db),
):
    return chatbot_service.list_documents(
        plant=plant,
        email=email,
        access_mode=access_mode,
        session_token=x_portal_session,
        db=db,
        car_id=car_id,
    )


# ---------------------------------------------------------------------------
# File management (standalone endpoints)
# ---------------------------------------------------------------------------

@router.post("/upload-file")
async def upload_file(
    token: str = Form(...),
    email: str = Form(...),
    file: UploadFile = File(...),
    target_action_type: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Upload a single supporting document for a CAR (stored in Azure Blob)."""
    return await car_service.upload_file_for_car(
        token=token,
        email=email,
        file=file,
        db=db,
        target_action_type=target_action_type,
    )


@router.delete("/delete-file/{document_id}")
async def delete_file(
    document_id: int,
    token: str,
    email: str,
    target_action_type: str | None = None,
    db: Session = Depends(get_db),
):
    """Delete a previously uploaded document from Azure Blob and the database."""
    return await car_service.delete_file_for_car(
        document_id=document_id,
        token=token,
        email=email,
        db=db,
        target_action_type=target_action_type,
    )


# ---------------------------------------------------------------------------
# Step 4 – Submit form
# ---------------------------------------------------------------------------

@router.post("/submit")
async def submit_car(
    token: str = Form(...),
    email: str = Form(...),
    implemented_solution: str = Form(...),
    # Optional, not just "may be blank": an empty multipart field is
    # indistinguishable from an absent one to Starlette's parser, so a
    # Form(...) here 422s outright for the immediate section (which has no
    # root cause to send) before this handler ever runs.
    root_cause: str | None = Form(None),
    portal_session_token: str | None = Form(None),
    portal_plant: str | None = Form(None),
    portal_access_mode: str = Form("auditee"),
    files: Optional[List[UploadFile]] = File(None),
    target_action_type: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """
    Submit the corrective action solution + root cause.
    Files are uploaded to Azure Blob Storage (audits/car/ folder).
    target_action_type ("corrective" | "immediate") selects which of a
    finding's linked rows this submission applies to; omit it to submit the
    row the token itself points at (today's behavior, unchanged).
    """
    return await car_service.submit_car_form(
        token=token,
        email=email,
        implemented_solution=implemented_solution,
        root_cause=root_cause,
        files=files,
        db=db,
        portal_session_token=portal_session_token,
        portal_plant=portal_plant,
        portal_access_mode=portal_access_mode,
        target_action_type=target_action_type,
    )


# ---------------------------------------------------------------------------
# Reassign responsible + "Copy to" recipients (auditee-triggered)
# ---------------------------------------------------------------------------

@router.post("/reassign")
async def reassign_car(
    data: ReassignCarInput,
    db: Session = Depends(get_db),
):
    """Auditee hands off the CAR to someone else. One-time only."""
    return await car_service.reassign_car(
        token=data.token,
        email=data.email,
        new_email=data.new_email,
        reason=data.reason,
        db=db,
        portal_session_token=data.portal_session_token,
        portal_plant=data.portal_plant,
        portal_access_mode=data.portal_access_mode,
    )


@router.post("/add-cc")
async def add_car_cc(
    data: AddCcInput,
    db: Session = Depends(get_db),
):
    """Auditee adds extra people to be copied on this CAR's notifications."""
    return await car_service.add_car_cc(
        token=data.token,
        email=data.email,
        cc_emails=data.cc_emails,
        db=db,
        portal_session_token=data.portal_session_token,
        portal_plant=data.portal_plant,
        portal_access_mode=data.portal_access_mode,
    )


# ---------------------------------------------------------------------------
# Unavailability
# ---------------------------------------------------------------------------

@router.post("/audits/unavailability")
def add_unavailability_for_audit(
    payload: AddUnavailabilityInput,
    db: Session = Depends(get_db),
):
    """Submit auditee leave request. Plant manager decides approval/rejection by email link."""
    return car_service.request_audit_unavailability_approval(
        db=db,
        start_date=payload.start_date,
        end_date=payload.end_date,
        reason=payload.reason,
        token=payload.token,
    )


@router.get("/audits/unavailability/decision", response_class=HTMLResponse)
def decide_unavailability_from_email_link(
    token: str,
    unavailability_id: int,
    decision: str = Query(..., pattern="^(approve|reject)$"),
    comment: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Plant manager action endpoint called from email links.
    It finalizes request and returns a small confirmation page.
    """
    return _process_unavailability_decision(
        db=db,
        token=token,
        unavailability_id=unavailability_id,
        decision=decision,
        comment=comment,
    )


@router.post("/audits/unavailability/decision", response_class=HTMLResponse)
def decide_unavailability_from_email_link_post(
    token: str = Form(...),
    unavailability_id: int = Form(...),
    decision: str = Form(...),
    comment: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    decision = (decision or "").strip().lower()
    if decision not in {"approve", "reject"}:
        return HTMLResponse(
            status_code=400,
            content="""
            <html><body style="font-family:Arial,sans-serif;background:#f8fafc;padding:24px;">
            <div style="max-width:640px;margin:auto;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:24px;">
              <h2 style="margin-top:0;color:#b91c1c;">Invalid Decision</h2>
              <p>Decision must be either approve or reject.</p>
            </div></body></html>
            """,
        )
    return _process_unavailability_decision(
        db=db,
        token=token,
        unavailability_id=unavailability_id,
        decision=decision,
        comment=comment,
    )


def _process_unavailability_decision(
    *,
    db: Session,
    token: str,
    unavailability_id: int,
    decision: str,
    comment: Optional[str],
):
    try:
        result = car_service.decide_audit_unavailability(
            db=db,
            token=token,
            unavailability_id=unavailability_id,
            decision=decision,
            comment=comment,
        )
    except HTTPException as exc:
        status = exc.status_code
        detail = str(exc.detail)
        if status == 409 and "already used" in detail.lower():
            title = "Decision Already Recorded"
            color = "#7c2d12"
            helper = (
                "This approval link is single-use. "
                "The request was already processed."
            )
        elif status == 410:
            title = "Link Expired"
            color = "#b45309"
            helper = "This decision link has expired. Please request a new leave submission."
        elif status == 404:
            title = "Invalid Link"
            color = "#b91c1c"
            helper = "The decision link is not valid. Please use the latest email."
        else:
            title = "Unable To Process Decision"
            color = "#b91c1c"
            helper = "An error occurred while processing this request."

        return HTMLResponse(
            status_code=status,
            content=f"""
            <html>
              <body style="font-family:Arial,sans-serif;background:#f8fafc;padding:24px;">
                <div style="max-width:640px;margin:auto;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:24px;">
                  <h2 style="margin-top:0;color:{color};">{title}</h2>
                  <p style="margin-bottom:8px;"><strong>Details:</strong> {detail}</p>
                  <p style="color:#475569;">{helper}</p>
                </div>
              </body>
            </html>
            """,
        )

    color = "#15803d" if result["status"] == "approved" else "#b91c1c"
    return f"""
    <html>
      <body style="font-family:Arial,sans-serif;background:#f8fafc;padding:24px;">
        <div style="max-width:640px;margin:auto;background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:24px;">
          <h2 style="margin-top:0;color:{color};">Decision recorded</h2>
          <p><strong>Audit:</strong> {result["audit_number"]}</p>
          <p><strong>Status:</strong> {result["status"]}</p>
          <p>{result["message"]}</p>
        </div>
      </body>
    </html>
    """


# ---------------------------------------------------------------------------
# Debug / utility endpoints
# ---------------------------------------------------------------------------

@router.get("/debug/{car_id}/due-date")
def debug_car_due_date(
    car_id: int,
    db: Session = Depends(get_db),
):
    """Show CAR due-date calculation details (debug)."""
    from app.models.CarUnavailability import AuditUnavailability
    from app.models.audit import Audit
    from app.utils.due_date import recompute_due_date_from_base

    car = db.query(CorrectiveAction).filter_by(id=car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")

    audit = db.query(Audit).filter_by(id=car.audit_id).first()
    unavailabilities = db.query(AuditUnavailability).filter_by(audit_id=audit.id).all()
    periods = [(u.start_date, u.end_date) for u in unavailabilities]

    new_due = None
    if car.due_date_base and car.created_at:
        new_due = recompute_due_date_from_base(
            created_at=car.created_at,
            plant=audit.plant,
            due_base=car.due_date_base,
            unavailability_periods=periods,
        )

    return {
        "car_id": car.id,
        "created_at": car.created_at,
        "due_date_base": car.due_date_base,
        "current_due_date": car.due_date,
        "calculated_due_date": new_due,
        "plant": audit.plant,
        "unavailability_periods": [
            {"start": p[0].isoformat(), "end": p[1].isoformat()}
            for p in periods
        ],
        "should_update": new_due != car.due_date if new_due else False,
    }


@router.get("/{car_id}/unavailability-impact")
def debug_unavailability_impact(
    car_id: int,
    db: Session = Depends(get_db),
):
    """Detailed day-by-day breakdown of unavailability impact on a CAR's due date."""
    from app.models.CarUnavailability import AuditUnavailability
    from app.models.audit import Audit
    from app.utils.due_date import build_holidays_for_plant, is_working_day
    from datetime import datetime, timedelta

    car = db.query(CorrectiveAction).filter_by(id=car_id).first()
    if not car:
        raise HTTPException(status_code=404, detail="CAR not found")

    audit = db.query(Audit).filter_by(id=car.audit_id).first()
    unavailabilities = db.query(AuditUnavailability).filter_by(audit_id=audit.id).all()
    periods = [
        (
            u.start_date.date() if isinstance(u.start_date, datetime) else u.start_date,
            u.end_date.date() if isinstance(u.end_date, datetime) else u.end_date,
        )
        for u in unavailabilities
    ]

    years = {car.created_at.date().year, car.due_date_base.year}
    for s, e in periods:
        years.add(s.year)
        years.add(e.year)
    holiday_set = build_holidays_for_plant(audit.plant, years)

    window_start = car.created_at.date() + timedelta(days=1)
    window_end = car.due_date_base

    day_by_day = []
    unavailable_workday_count = 0
    current = window_start

    while current <= window_end:
        is_work = is_working_day(current, holiday_set)
        is_unavail = any(s <= current <= e for s, e in periods)

        status = []
        if not is_work:
            if current.weekday() >= 5:
                status.append("weekend")
            if current in holiday_set:
                status.append("holiday")
        else:
            status.append("workday")
            if is_unavail:
                status.append("unavailable")
                unavailable_workday_count += 1

        day_by_day.append(
            {
                "date": current.isoformat(),
                "day_name": current.strftime("%A"),
                "status": status,
                "counts": is_work and is_unavail,
            }
        )
        current += timedelta(days=1)

    return {
        "car_id": car.id,
        "created_at": car.created_at.isoformat(),
        "due_date_base": car.due_date_base.isoformat(),
        "current_due_date": car.due_date.isoformat(),
        "plant": audit.plant,
        "window": {"start": window_start.isoformat(), "end": window_end.isoformat()},
        "unavailability_periods": [
            {"start": s.isoformat(), "end": e.isoformat()} for s, e in periods
        ],
        "holidays": [
            d.isoformat()
            for d in sorted(holiday_set)
            if window_start <= d <= window_end
        ],
        "unavailable_workdays_count": unavailable_workday_count,
        "day_by_day": day_by_day,
        "expected_new_due": (
            car.due_date_base + timedelta(days=unavailable_workday_count)
        ).isoformat(),
    }


@router.post("/reminders/trigger")
async def trigger_reminders_manually(
    days: int = Query(
        default=None,
        description="Specify 1, 2 or 3 working days, or omit to trigger all",
    ),
):
    """Manually trigger the CAR reminder check (useful for testing)."""
    try:
        from app.services.car_reminder_scheduler import check_and_send_reminders

        results = []
        if days is None:
            check_and_send_reminders(3)
            check_and_send_reminders(2)
            check_and_send_reminders(1)
            results = ["3-day reminders", "2-day reminders", "1-day reminders"]
        elif days in [1, 2, 3]:
            check_and_send_reminders(days)
            results = [f"{days}-day reminders"]
        else:
            raise HTTPException(status_code=400, detail="Days must be 1, 2 or 3")

        return {
            "status": "success",
            "message": f"CAR reminder check completed for: {', '.join(results)}",
            "triggered": results,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error in manual reminder trigger: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/reminders/preview")
async def preview_reminder_emails(
    days: int = Query(default=3, description="Working days before due date (1, 2 or 3)"),
    db: Session = Depends(get_db),
):
    """Preview how CARs will be grouped into reminder emails."""
    try:
        today = date.today()
        candidates = db.query(CorrectiveAction).filter(
            and_(
                CorrectiveAction.due_date != None,
                CorrectiveAction.due_date >= today,
                CorrectiveAction.status == "pending",
            )
        ).all()
        cars = []
        for car in candidates:
            audit = car.audit
            if not audit or not audit.plant or not car.due_date:
                continue
            remaining = get_remaining_working_days(
                from_date=today,
                due_date=car.due_date,
                plant=str(audit.plant).lower(),
            )
            if remaining == days:
                cars.append(car)

        if not cars:
            return {
                "days_before": days,
                "working_days_before": days,
                "total_cars": 0,
                "total_emails": 0,
                "grouped_emails": [],
            }

        def get_car_type(answer):
            if not answer:
                return "Observation"
            if answer.fail:
                return "Critical"
            if answer.improve:
                return "Amélioration"
            return "Observation"

        grouped: dict = defaultdict(list)
        for car in cars:
            if car.auditee and car.auditee.email and car.audit:
                key = (car.audit_id, car.auditee.email, car.audit.audit_number)
                grouped[key].append(car)

        grouped_emails = [
            {
                "audit_id": audit_id,
                "audit_number": audit_number,
                "recipient": auditee_email,
                "car_count": len(car_list),
                "cars": [
                    {
                        "id": c.id,
                        "due_date": c.due_date.isoformat(),
                        "status": c.status,
                        "type": get_car_type(c.answer),
                        "question": (
                            c.answer.question.description[:50] + "..."
                            if c.answer
                            and c.answer.question
                            and c.answer.question.description
                            else "N/A"
                        ),
                        "finding": (
                            c.finding or (c.answer.finding_text if c.answer else None)
                        )[:50] + "..."
                        if ((c.answer and c.answer.finding_text) or c.finding)
                        else "N/A",
                        "reason": (
                            c.reason_why[:50] + "..."
                            if c.reason_why and len(c.reason_why) > 50
                            else c.reason_why or "N/A"
                        ),
                    }
                    for c in car_list
                ],
            }
            for (audit_id, auditee_email, audit_number), car_list in grouped.items()
        ]

        return {
            "days_before": days,
            "working_days_before": days,
            "total_cars": len(cars),
            "total_emails": len(grouped_emails),
            "grouped_emails": grouped_emails,
        }

    except Exception as exc:
        logger.error("Error previewing reminders: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
