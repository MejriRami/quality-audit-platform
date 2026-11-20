import asyncio
from datetime import datetime
import logging
from pathlib import Path
from typing import List, Optional
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session, joinedload
from app.config.database import get_db
from app.models.audit import Audit
from app.models.audit_reschedule_history import AuditRescheduleHistory
from app.models.user import User
from app.schemas.QuestionAnswer import AuditAnswersResponse
from app.schemas.auditSchema.auditSchema import (
    AuditAuditeeUpdateRequest,
    AuditCancelRequest,
    AuditDraftRequest,
    AuditDraftResponse,
    AuditListResponse,
    AuditPickerItem,
    AuditPlanCreate,
    AuditPlanningDetailsResponse,
    AuditPlanningDetailsUpdate,
    AuditPlanningSyncResponse,
    AuditRescheduleHistoryResponse,
    AuditRescheduleRequest,
    AuditResponse,
    ExecuteAuditRequest,
    QuestionResponse,
    auditeeAvailability,
    PaginatedAuditResponse,
)
from app.services import auth_service
from app.services.audit_service import (
    cancel_audit,
    check_auditee_availability,
    execute_audit_service,
    get_all_audits,
    get_audit_answers,
    get_audit_draft,
    get_audit_planning_details,
    get_planned_or_rescheduled_audits_by_auditor,
    getAuditsByAuditor,
    getQuestionsByAudit,
    plan_audit,
    process_outlook_webhook_notification,
    delete_audit,
    reschedule_audit,
    resolve_history_display_action_type,
    save_audit_draft,
    sync_audit_planning_event,
    update_audit_auditees,
    update_audit_planning_details,
    get_vda_questions_by_audit,
)
from app.routers.audit_report import get_audit_data_for_report, persist_report_to_sharepoint
from app.services.audit_report_service import generate_audit_report
from app.services.car_service import get_or_create_unavailability_form_token
from app.services.role_access_service import has_auditor_role
from app.utils.due_date import get_holiday_details_for_plant
from app.utils.send_car_email import (
    build_combined_report_email_body,
    build_unavailability_url,
    send_email_with_attachment,
)
from app.utils.utility import map_audit_to_picker

router = APIRouter(prefix="/audits", tags=["Audits"])
logger = logging.getLogger(__name__)
REPORTS_DIR = Path("app/reports")
REPORTS_DIR.mkdir(exist_ok=True)


def require_auditor_role(current_user: User) -> User:
    if not has_auditor_role(current_user):
        raise HTTPException(
            status_code=403,
            detail="You are not auditor. Only auditors can perform this action.",
        )
    return current_user


@router.post("/plan", response_model=AuditResponse)
async def plan_audit_endpoint(
    payload: AuditPlanCreate,
    allow_unavailable_auditee: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
):
    require_auditor_role(current_user)
    if allow_unavailable_auditee:
        payload.allow_unavailable_auditee = True
    return await plan_audit(db, payload)


@router.get("/{audit_id}/planning-details", response_model=AuditPlanningDetailsResponse)
def get_planning_details(
    audit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
):
    require_auditor_role(current_user)
    return get_audit_planning_details(audit_id, db)


@router.patch(
    "/{audit_id}/planning-details", response_model=AuditPlanningDetailsResponse
)
async def update_planning_details(
    audit_id: int,
    payload: AuditPlanningDetailsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
):
    require_auditor_role(current_user)
    return await update_audit_planning_details(audit_id, payload, db, actor=current_user)


@router.post(
    "/{audit_id}/planning-details/send-calendar",
    response_model=AuditPlanningSyncResponse,
)
async def send_planning_calendar(
    audit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
):
    require_auditor_role(current_user)
    return await sync_audit_planning_event(audit_id, db)


@router.get("/all", response_model=AuditListResponse)
def list_audits(db: Session = Depends(get_db)):
    audits = get_all_audits(db)
    return {"audits": audits}


# class AuditRequestCreate(BaseModel):
#     auditor_email: str
#     subject: str
#     to_emails: list[str]
# @router.post("/request")
# async def request_audit_endpoint(

#     payload: AuditRequestCreate,
# ):
#     body_email=build_auditee_request_body_html(
#     "noel",
#     "it",
#     "it",
#     "13/11/200",
#     "",
#     "",
#     "Auditor 1 / Auditor 2",
#     "this is test message")
#     await send_mail_via_graph(payload.auditor_email,payload.subject,body_email,payload.to_emails)
#     # return await request_audit( payload)


@router.get("/auditee")
async def check_disponibility(
    data: auditeeAvailability,
    db: Session = Depends(get_db),
):

    return await check_auditee_availability(data, db)


@router.get("/auditor/{auditor_id}", response_model=PaginatedAuditResponse)
def getAuditsByAuditor_route(
    auditor_id: int,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
    db: Session = Depends(get_db),
):
    return getAuditsByAuditor(db, auditor_id, page, per_page)


@router.get(
    "/auditor/{auditor_id}/pickable-audits",
    response_model=list[AuditPickerItem],
)
def get_pickable_audits_for_auditor_route(
    auditor_id: int,
    db: Session = Depends(get_db),
):
    audits = get_planned_or_rescheduled_audits_by_auditor(auditor_id, db)
    return [map_audit_to_picker(a) for a in audits]


@router.get("/plants/{plant}/holidays")
def get_plant_holidays(
    plant: str,
    year: Optional[int] = None,
):
    selected_year = year or datetime.utcnow().year
    try:
        holiday_map = get_holiday_details_for_plant(plant, {selected_year})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "plant": plant,
        "year": selected_year,
        "holidays": [
            {"date": holiday_date.isoformat(), "name": holiday_name}
            for holiday_date, holiday_name in holiday_map.items()
        ],
    }


@router.get("/{audit_id}/questions", response_model=List[QuestionResponse])
def getAuditQuestions(audit_id: int, db: Session = Depends(get_db)):
    return getQuestionsByAudit(audit_id, db)


@router.patch("/{audit_id}/reschedule", response_model=AuditResponse)
async def reschedule_audit_route(
    audit_id: int,
    data: AuditRescheduleRequest,
    allow_unavailable_auditee: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
):
    require_auditor_role(current_user)
    if allow_unavailable_auditee:
        data.allow_unavailable_auditee = True
    return await reschedule_audit(audit_id, data, db)


@router.patch("/{audit_id}/cancel", response_model=AuditResponse)
async def cancel_audit_route(
    audit_id: int,
    data: AuditCancelRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
):
    require_auditor_role(current_user)
    return await cancel_audit(audit_id, data, db)


@router.delete("/{audit_id}")
def delete_audit_route(
    audit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
):
    require_auditor_role(current_user)
    return delete_audit(audit_id, db)


@router.patch("/{audit_id}/auditees", response_model=AuditResponse)
async def update_audit_auditees_route(
    audit_id: int,
    data: AuditAuditeeUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
):
    require_auditor_role(current_user)
    return await update_audit_auditees(audit_id, data, db)


@router.get("/{audit_id}/history", response_model=List[AuditRescheduleHistoryResponse])
def get_reschedule_history(audit_id: int, db: Session = Depends(get_db)):
    history = (
        db.query(AuditRescheduleHistory)
        .options(joinedload(AuditRescheduleHistory.changed_by_user))
        .filter(AuditRescheduleHistory.audit_id == audit_id)
        .order_by(AuditRescheduleHistory.created_at.desc())
        .all()
    )
    return [
        AuditRescheduleHistoryResponse(
            id=item.id,
            action_type=resolve_history_display_action_type(
                item.action_type, item.reason
            ),
            old_date=item.old_date,
            new_date=item.new_date,
            reason=item.reason,
            changed_by=getattr(item.changed_by_user, "email", None),
            created_at=item.created_at,
        )
        for item in history
    ]


# score calculation missing here
# create AT always minus 1hour from my local time
@router.post("/{audit_id}/execute")
def execute_audit(
    audit_id: int,
    payload: ExecuteAuditRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
):
    require_auditor_role(current_user)
    result = execute_audit_service(
        db=db,
        audit_id=audit_id,
        payload=payload,
    )

    # Auto-send report after execution.
    p1_result = ((result.get("vda_result") or {}).get("p1_result") or {})
    has_vda_sections = bool((result.get("vda_result") or {}).get("elements"))

    if not p1_result:
        # Non-VDA/P1 audits: generate the report once, persist it to SharePoint
        # (so it's already attached to the audit without a manual "Generate Report"
        # click), then send one personalized email per auditee combining the report
        # attachment with that audit's CAR table (if any) and the portal/leave links.
        try:
            audit = (
                db.query(Audit)
                .options(
                    joinedload(Audit.auditor),
                    joinedload(Audit.auditees),
                    joinedload(Audit.questionnaire),
                )
                .filter(Audit.id == audit_id)
                .first()
            )
            if not audit:
                raise HTTPException(status_code=404, detail="Audit not found")

            auditees = [a for a in (audit.auditees or []) if a.email]
            cc_recipients = [
                e for e in [
                    getattr(getattr(audit, "auditor", None), "email", None),
                    getattr(audit, "supervisor_email", None),
                ] if e
            ]

            if auditees:
                audit_data = get_audit_data_for_report(audit_id, db)

                audit_number_safe = (audit.audit_number or f"audit-{audit_id}").replace("/", "_").replace(" ", "_")
                temp_filename = f"audit_report_{audit_number_safe}_{uuid4().hex[:8]}.pdf"
                temp_path = REPORTS_DIR / temp_filename
                report_path = Path(generate_audit_report(audit_data, str(temp_path), logo_path=None))

                cars = result.get("cars", [])
                subject = f"Audit Report - {audit.audit_number}"
                if cars:
                    subject += " - Corrective Actions Required"

                async def _persist_and_send():
                    await persist_report_to_sharepoint(
                        audit=audit,
                        report_path=report_path,
                        filename=temp_filename,
                        plant_name=audit_data.get("plant"),
                        db=db,
                    )
                    for auditee in auditees:
                        unavailability_token = get_or_create_unavailability_form_token(
                            db=db,
                            audit_id=audit_id,
                            email=auditee.email,
                        )
                        body_html = build_combined_report_email_body(
                            auditee_name=auditee.email.split("@")[0],
                            audit_reference=audit.audit_number,
                            plant=audit.plant,
                            cars=cars,
                            unavailability_url=build_unavailability_url(unavailability_token),
                        )
                        await send_email_with_attachment(
                            recipients=[auditee.email],
                            cc=cc_recipients or None,
                            subject=subject,
                            body_html=body_html,
                            attachment_path=str(report_path),
                            attachment_filename=temp_filename,
                            db=db,
                            context="audit_report_auto",
                        )

                asyncio.run(_persist_and_send())

                try:
                    report_path.unlink(missing_ok=True)
                except Exception as cleanup_error:
                    logger.warning(f"Could not delete temporary audit report file: {cleanup_error}")
            else:
                logger.warning(f"Audit report auto-send skipped for audit {audit_id}: no auditee recipients")
        except Exception as report_email_error:
            logger.exception(f"Audit report auto-send failed for audit {audit_id}: {report_email_error}")
            result["report_email_error"] = str(report_email_error)

    if p1_result:
        try:
            audit = (
                db.query(Audit)
                .options(
                    joinedload(Audit.auditor),
                    joinedload(Audit.auditees),
                    joinedload(Audit.questionnaire),
                )
                .filter(Audit.id == audit_id)
                .first()
            )
            if not audit:
                raise HTTPException(status_code=404, detail="Audit not found")

            to_recipients = [a.email for a in (audit.auditees or []) if a.email]
            cc_recipients = [
                e for e in [
                    getattr(getattr(audit, "auditor", None), "email", None),
                    getattr(audit, "supervisor_email", None),
                ] if e
            ]

            if to_recipients:
                audit_data = get_audit_data_for_report(audit_id, db)
                report_is_combined = has_vda_sections and bool(audit_data.get("p1_result"))

                audit_number_safe = (audit.audit_number or f"audit-{audit_id}").replace("/", "_").replace(" ", "_")
                if report_is_combined:
                    temp_filename = f"vda_combined_report_{audit_number_safe}_{uuid4().hex[:8]}.pdf"
                else:
                    temp_filename = f"vda_p1_report_{audit_number_safe}_{uuid4().hex[:8]}.pdf"
                temp_path = REPORTS_DIR / temp_filename
                report_path = Path(generate_audit_report(audit_data, str(temp_path), logo_path=None))

                if report_is_combined:
                    p1_class = audit_data.get("p1_result", {}).get("classification", "N/A")
                    p1_label = audit_data.get("p1_result", {}).get("label", "N/A")
                    email_body = f"""
                    <p>Hello,</p>
                    <p>The audit has been executed and the combined report is attached.</p>
                    <p><strong>Audit:</strong> {audit.audit_number}<br/>
                    <strong>Plant:</strong> {audit.plant or "N/A"}<br/>
                    <strong>P1 classification:</strong> {p1_class} - {p1_label}</p>
                    <p>The PDF includes both the P1 potential analysis and the VDA 6.3 sections.</p>
                    <p>Best regards,<br/>Audit Team</p>
                    """
                    subject = f"Combined VDA / P1 Audit Report - {audit.audit_number}"
                else:
                    p1_class = p1_result.get("classification", "N/A")
                    p1_label = p1_result.get("label", "N/A")
                    email_body = f"""
                    <p>Hello,</p>
                    <p>The VDA P1 audit has been executed.</p>
                    <p><strong>Audit:</strong> {audit.audit_number}<br/>
                    <strong>Plant:</strong> {audit.plant or "N/A"}<br/>
                    <strong>Final classification:</strong> {p1_class} - {p1_label}</p>
                    <p>Please find the dedicated P1 report attached.</p>
                    <p>Best regards,<br/>Audit Team</p>
                    """
                    subject = f"VDA P1 Audit Report - {audit.audit_number}"

                async def _persist_and_send_p1():
                    await persist_report_to_sharepoint(
                        audit=audit,
                        report_path=report_path,
                        filename=temp_filename,
                        plant_name=audit_data.get("plant"),
                        db=db,
                    )
                    await send_email_with_attachment(
                        recipients=to_recipients,
                        cc=cc_recipients or None,
                        subject=subject,
                        body_html=email_body,
                        attachment_path=str(report_path),
                        attachment_filename=temp_filename,
                        db=db,
                        context="p1_report_auto",
                    )

                asyncio.run(_persist_and_send_p1())

                try:
                    report_path.unlink(missing_ok=True)
                except Exception as cleanup_error:
                    logger.warning(f"Could not delete temporary P1 report file: {cleanup_error}")
            else:
                logger.warning(f"P1 report auto-send skipped for audit {audit_id}: no auditee recipients")
        except Exception as p1_email_error:
            logger.exception(f"P1 report auto-send failed for audit {audit_id}: {p1_email_error}")
            result["p1_report_email_error"] = str(p1_email_error)

    return result


@router.patch("/{audit_id}/draft", response_model=AuditDraftResponse)
def save_draft(
    audit_id: int,
    data: AuditDraftRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
):
    require_auditor_role(current_user)
    return save_audit_draft(audit_id, data, db)


"""
─── NEW: Load draft ────────────────────────────────────────────
"""


@router.get("/{audit_id}/draft", response_model=AuditDraftResponse)
def get_draft(audit_id: int, db: Session = Depends(get_db)):
    return get_audit_draft(audit_id, db)


LAST_WEBHOOK = {"received_at": None, "headers": None, "body": None}


@router.post("/webhook/outlook")
async def outlook_webhook(
    request: Request,
    validationToken: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Microsoft Graph webhook endpoint for Outlook calendar event updates
    Handles both validation and notifications
    """

    # 1. Handle validation during subscription creation
    if validationToken:
        return Response(content=validationToken, media_type="text/plain")

    # 2. Process notifications
    try:
        payload = await request.json()

        # Store for debugging
        LAST_WEBHOOK["received_at"] = datetime.utcnow().isoformat()
        LAST_WEBHOOK["headers"] = dict(request.headers)
        LAST_WEBHOOK["body"] = payload

        print("📨 Received webhook notification")
        print(f"   Notifications count: {len(payload.get('value', []))}")

        # Process each notification
        for notif in payload.get("value", []):
            # Verify clientState for security
            client_state = notif.get("clientState")
            if client_state != "audit-secret":
                print(f"⚠️ Invalid clientState: {client_state}")
                raise HTTPException(status_code=403, detail="Invalid clientState")

            # Process the notification
            await process_outlook_webhook_notification(notif, db)

        return {"status": "ok", "processed": len(payload.get("value", []))}

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/last-webhook")
def debug_last_webhook():
    return LAST_WEBHOOK


@router.get("/{audit_id}/vda-questions")
def get_vda_questions(audit_id: int, db: Session = Depends(get_db)):
    return get_vda_questions_by_audit(audit_id, db)


@router.get("/{audit_id}/answers", response_model=AuditAnswersResponse)
def get_all_audit_answers(
    audit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
):
    return get_audit_answers(audit_id, db, current_user)


