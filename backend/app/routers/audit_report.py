
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict
import json
import logging

from app.config.database import get_db
from app.models.audit import Audit
from app.models.audit_answr import AuditAnswer
from app.models.corrective_action import CorrectiveAction
from app.models.questionnaire import Questionnaire
from app.models.user import User
from app.schemas.SendReportEmailRequest import SendReportEmailRequest
from app.schemas.ConsolidateThemeReportRequest import ConsolidateThemeReportRequest
from app.services import auth_service
from app.services.audit_report_service import create_email_body, generate_audit_report
from app.services.consolidation_report_service import (
    build_consolidated_findings,
    generate_consolidated_findings_report,
    generate_consolidated_vda_report,
)
from app.services.role_access_service import can_view_silent_box, has_auditor_role
from app.services.scoring_service import resolve_report_profile
from app.services.vda_scoring_service import VDA_ELEMENTS, compute_vda_results
from app.services.sharepoint_audit_storage import SharePointAuditStorage, SharePointConfig
from app.utils.send_car_email import send_email_with_attachment

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


def require_auditor_role(current_user: User) -> User:
    if not has_auditor_role(current_user):
        raise HTTPException(
            status_code=403,
            detail="You are not auditor. Only auditors can perform this action.",
        )
    return current_user

# Configure SharePoint storage
sp_storage = SharePointAuditStorage(
    SharePointConfig(
        hostname="northwindgroup.sharepoint.com",
        site_path="/sites/Northwind-internal-Audits",
        library_name="Documents",
        root_folder="audit-reports-2026",
    )
)

# Configure report storage directory (for temporary files only)
REPORTS_DIR = Path("app/reports")
REPORTS_DIR.mkdir(exist_ok=True)

# Logo path
LOGO_PATH = Path("app/assets/logo-northwind.jpg")


# Helper functions to encode/decode SharePoint metadata in report_url
def encode_sharepoint_url(drive_id: str, item_id: str, web_url: str, sp_path: str) -> str:
    """Encode SharePoint metadata as JSON string in report_url field"""
    metadata = {
        "drive_id": drive_id,
        "item_id": item_id,
        "web_url": web_url,
        "path": sp_path,
        "type": "sharepoint"
    }
    return f"sp://{json.dumps(metadata)}"


def decode_sharepoint_url(report_url: str) -> Optional[Dict[str, str]]:
    """Decode SharePoint metadata from report_url field"""
    if not report_url or not report_url.startswith("sp://"):
        return None
    
    try:
        json_str = report_url[5:]
        return json.loads(json_str)
    except Exception as e:
        logger.error(f"Failed to decode SharePoint URL: {e}")
        return None


def is_sharepoint_url(report_url: str) -> bool:
    """Check if report_url is a SharePoint URL"""
    return report_url and report_url.startswith("sp://")


async def persist_report_to_sharepoint(
    *,
    audit: Audit,
    report_path: Path,
    filename: str,
    plant_name: str,
    db: Session,
) -> str:
    """
    Upload a generated report PDF to SharePoint and point audit.report_url at it,
    replacing any previously persisted report for this audit. Shared by the manual
    "Generate Report" action and the auto-send-on-execute flow so both leave the
    audit with a persisted report (no separate manual generation step needed).
    Returns the SharePoint web URL.
    """
    old_sp_metadata = decode_sharepoint_url(audit.report_url) if audit.report_url else None

    upload_result = await sp_storage.upload_report_to_plant(
        plant_name=plant_name or "Unknown-Plant",
        pdf_path=report_path,
        filename=filename,
    )

    if old_sp_metadata:
        try:
            await sp_storage.delete_by_item_id(
                old_sp_metadata["drive_id"], old_sp_metadata["item_id"]
            )
        except Exception as e:
            logger.warning(f"Could not delete old SharePoint report for audit {audit.id}: {e}")

    audit.report_url = encode_sharepoint_url(
        drive_id=upload_result["drive_id"],
        item_id=upload_result["file"]["id"],
        web_url=upload_result["file"]["webUrl"],
        sp_path=upload_result["file"]["path"],
    )
    db.commit()
    return upload_result["file"]["webUrl"]


# Report profiles whose audits can be merged and re-scored as one VDA 6.3
# virtual audit by the consolidation report.
VDA_CONSOLIDATION_PROFILES = {"VDA", "VDA_COMBINED"}


def _question_element_code(question: dict) -> str:
    """Return a normalized question element code such as P1, P2, or P7."""
    element = str(question.get("element") or "").strip().upper()
    if element:
        return element

    question_code = str(question.get("question_code") or "").strip().upper()
    if question_code:
        return question_code.split(".")[0]

    chapter = str(question.get("chapter") or "").strip().upper()
    if chapter:
        return chapter.split(".")[0]

    return ""


def _build_p1_result(
    detailed_questions: list[dict],
    *,
    potential_analysis_questionnaire_id: Optional[int] = None,
) -> Optional[dict]:
    """Build a P1 (Potential Analysis) summary from persisted audit answers.

    When potential_analysis_questionnaire_id is given, only answers whose
    question belongs to that linked questionnaire count (merged VDA 6.3 +
    Potential Analysis audit). When it's None, every answer counts (legacy
    standalone "P1-Potential Analysis" audit, where the whole audit IS the
    potential analysis).
    """
    if potential_analysis_questionnaire_id is not None:
        p1_questions = [
            q for q in detailed_questions
            if q.get("questionnaire_id") == potential_analysis_questionnaire_id
        ]
    else:
        p1_questions = detailed_questions

    if not p1_questions:
        return None

    def _score_value(question: dict) -> int:
        try:
            return int(question.get("value"))
        except (TypeError, ValueError):
            return -1

    red = sum(1 for q in p1_questions if _score_value(q) == 0)
    yellow = sum(1 for q in p1_questions if _score_value(q) == 4)
    green = sum(1 for q in p1_questions if _score_value(q) == 10)
    ne = sum(1 for q in p1_questions if _score_value(q) == -1)

    if red >= 1 or yellow > 12:
        classification = "R"
        label = "Barred supplier"
    elif yellow <= 6:
        classification = "G"
        label = "Approved supplier"
    else:
        classification = "Y"
        label = "Conditionally approved supplier"

    return {
        "red": red,
        "yellow": yellow,
        "green": green,
        "ne": ne,
        "classification": classification,
        "label": label,
    }


SILENT_BOX_TAG = "[SB]"


def get_audit_data_for_report(audit_id: int, db: Session, include_silent_box: bool = False) -> dict:
    """Fetch and format all audit data needed for report generation.

    include_silent_box: build the internal "complete" report, which keeps
    Silent Box findings (tagged [SB]) instead of dropping them. Never use it
    for the report that is stored on SharePoint or emailed to auditees.
    """
    from sqlalchemy.orm import joinedload
    
    audit = db.query(Audit)\
        .options(
            joinedload(Audit.answers).joinedload(AuditAnswer.question),
            joinedload(Audit.auditor),
            joinedload(Audit.second_auditor),
            joinedload(Audit.auditees),
            joinedload(Audit.questionnaire).joinedload(Questionnaire.audit_type),
            joinedload(Audit.questionnaire).joinedload(Questionnaire.framework),
        )\
        .filter(Audit.id == audit_id)\
        .first()
    
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    
    # Calculate statistics
    answers = audit.answers
    # Silent Box answers are tracked internally but must never appear in the
    # printed/exported report (findings list or summary counts) -- except in
    # the internal complete report.
    visible_answers = [
        a for a in answers
        if include_silent_box or not getattr(a, "silent_box", False)
    ]
    total_pass = sum(1 for a in visible_answers if a.pass_)
    total_fail = sum(1 for a in visible_answers if a.fail)
    total_improve = sum(1 for a in visible_answers if a.improve)
    total_not_audited = sum(1 for a in visible_answers if not (a.pass_ or a.fail or a.improve))
    
    auditees = ", ".join([aa.email for aa in audit.auditees]) if audit.auditees else "N/A"
    
    def format_datetime(date_field):
        if date_field:
            if isinstance(date_field, str):
                return date_field
            return date_field.strftime("%Y-%m-%d %H:%M")
        return "N/A"
    
    def format_date_only(date_field):
        if date_field:
            if isinstance(date_field, str):
                return date_field
            return date_field.strftime("%Y-%m-%d")
        return "N/A"
    
    # Main auditor first, then the optional second auditor, so every report
    # layout that prints "auditor" credits both of them.
    auditor_names = [
        f"{user.first_name} {user.last_name}"
        for user in (audit.auditor, getattr(audit, "second_auditor", None))
        if user
    ]
    auditor_name = ", ".join(auditor_names) or "N/A"
    
    audit_type = "N/A"
    questionnaire_name = None
    
    if audit.questionnaire:
        questionnaire_name = audit.questionnaire.name
        if audit.questionnaire.audit_type:
            audit_type = audit.questionnaire.audit_type.value
        else:
            audit_type = audit.questionnaire.name
    
    is_iatf_nc_mode = any(
        answer.question_id is None and answer.classification is not None 
        for answer in audit.answers
    )
    
    detailed_questions = []

    for answer in visible_answers:
        try:
            if answer.pass_:
                status = 'pass'
            elif answer.fail:
                status = 'fail'
            elif answer.improve:
                status = 'improve'
            else:
                status = 'not_audited'
            
            if is_iatf_nc_mode and answer.question_id is None:
                question_data = {
                    'question_id': None,
                    'identifer': answer.identifier,
                    'question_text': answer.finding_text or 'No description',
                    'chapter': answer.standard_paragraph or 'N/A',
                    'value': answer.value if answer.value is not None else 0,
                    'status': status,
                    'finding_text': answer.finding_text if answer.finding_text else '',
                    'note': answer.note if hasattr(answer, 'note') and answer.note else '',
                    'critical_value': 0,
                    'process': answer.process if answer.process else 'N/A',
                    'standard_paragraph': answer.standard_paragraph if answer.standard_paragraph else 'N/A',
                    'classification': answer.classification if answer.classification else 'N/A',
                    'standard': 'IATF 16949:2016',
                }
            else:
                question_text = "Question not found"
                if answer.question:
                    question_text = answer.question.description
                elif answer.question_text:
                    # Open audit: question typed by the auditor.
                    question_text = answer.question_text
                else:
                    logger.warning(f"No question found for answer {answer.id}")
                
                question_data = {
                    'question_id': answer.question_id,
                    'identifer': answer.identifier,
                    'question_text': question_text,
                    'chapter': answer.question.chapter if answer.question and answer.question.chapter else 'Unknown',
                    'question_code': answer.question.question_code if answer.question and answer.question.question_code else None,
                    'element': answer.question.element if answer.question and answer.question.element else None,
                    'questionnaire_id': answer.question.questionnaire_id if answer.question else None,
                    'value': answer.value if answer.value is not None else 0,
                    'status': status,
                    'finding_text': answer.finding_text if answer.finding_text else '',
                    'note': answer.note if hasattr(answer, 'note') and answer.note else '',
                    'critical_value': answer.question.critical_value if answer.question else 0
                }
            
            answer_cars = db.query(CorrectiveAction).filter(
                CorrectiveAction.audit_answer_id == answer.id
            ).order_by(CorrectiveAction.action_type).all()

            def _serialize_cars(cars):
                return [
                    {
                        'action_type': ca.action_type,
                        'status': ca.status if ca.status else 'unknown',
                        'car_identifer': ca.identifier if ca.identifier else '',
                        'reason_why': ca.reason_why if ca.reason_why else '',
                        'due_date': format_date_only(ca.due_date) if ca.due_date else 'N/A',
                        'submitted_at': format_datetime(ca.submitted_at) if ca.submitted_at else 'Not submitted',
                        'implemented_solution': ca.implemented_solution if ca.implemented_solution else '',
                        # Only set on the immediate-action row (its due_date is
                        # NULL by design -- see corrective_action.py -- these
                        # carry its 24h/48h deadlines instead).
                        'submission_due_at': format_datetime(ca.submission_due_at) if ca.submission_due_at else None,
                        'closure_due_at': format_datetime(ca.closure_due_at) if ca.closure_due_at else None,
                    }
                    for ca in cars
                ]

            # Requirement CARs belong to their own requirement row below.
            corrective_actions = [
                ca for ca in answer_cars if ca.audit_answer_requirement_id is None
            ]
            if corrective_actions:
                question_data['corrective_action'] = _serialize_cars(corrective_actions)

            if getattr(answer, "silent_box", False):
                # Only reachable in the complete report: tag the fields each
                # layout prints (IATF process column, question / finding
                # text) so hidden findings stand out.
                question_data['silent_box'] = True
                for key in ('process', 'question_text', 'finding_text'):
                    value = str(question_data.get(key) or '').strip()
                    if value or key != 'finding_text':
                        question_data[key] = f"{SILENT_BOX_TAG} {value}".strip()

            detailed_questions.append(question_data)

            # VDA sub-requirements are scored independently of the parent
            # question: every requirement finding (0/4/6/8) is listed as its
            # own row so the report shows all non-conformities.
            cars_by_requirement: dict[int, list] = {}
            for ca in answer_cars:
                if ca.audit_answer_requirement_id is not None:
                    cars_by_requirement.setdefault(ca.audit_answer_requirement_id, []).append(ca)
            for req in sorted(answer.requirements or [], key=lambda r: r.id):
                req_value = int(req.value) if req.value is not None else None
                req_cars = cars_by_requirement.get(req.id, [])
                if req_value not in (0, 4, 6, 8) and not req_cars:
                    continue
                q_req = req.question_requirement
                req_code = (q_req.requirement_code if q_req else None) or ''
                req_row = dict(question_data)
                req_row.pop('corrective_action', None)
                req_row.update({
                    'is_requirement': True,
                    'question_text': (
                        f"{req_code}: {q_req.description}" if req_code and q_req
                        else (q_req.description if q_req else 'Requirement')
                    ),
                    'value': req_value if req_value is not None else 0,
                    'status': 'fail' if req_value is not None and req_value < (question_data.get('critical_value') or 6) else 'improve',
                    'finding_text': req.finding_text or '',
                })
                if question_data.get('question_code') and req_code:
                    req_row['question_code'] = f"{question_data['question_code']} {req_code}"
                if req_cars:
                    req_row['corrective_action'] = _serialize_cars(req_cars)
                detailed_questions.append(req_row)

        except Exception as e:
            logger.error(f"Error processing answer {answer.id}: {str(e)}")
            continue

    # Migrated (Monday) CARs are linked to the audit only (audit_answer_id is
    # NULL): attach them to the matching question by text, else list them as
    # their own finding rows so closed NCs still appear in the report.
    unlinked_cars = []
    if (audit.audit_number or "").startswith("M-"):
        unlinked_cars = db.query(CorrectiveAction).filter(
            CorrectiveAction.audit_id == audit.id,
            CorrectiveAction.audit_answer_id.is_(None),
        ).order_by(CorrectiveAction.id).all()
    for ca in unlinked_cars:
        car_row = {
            'action_type': ca.action_type,
            'status': ca.status if ca.status else 'unknown',
            'car_identifer': ca.identifier if ca.identifier else '',
            'reason_why': ca.reason_why if ca.reason_why else '',
            'due_date': format_date_only(ca.due_date) if ca.due_date else 'N/A',
            'submitted_at': format_datetime(ca.submitted_at) if ca.submitted_at else 'Not submitted',
            'implemented_solution': ca.implemented_solution if ca.implemented_solution else '',
            'submission_due_at': None,
            'closure_due_at': None,
        }
        question_text = (ca.migrated_question_text or '').strip()
        target = next(
            (q for q in detailed_questions
             if question_text and (q.get('question_text') or '').strip() == question_text),
            None,
        )
        if target is None:
            target = {
                'question_id': None,
                'identifer': ca.identifier,
                'question_text': question_text or ca.finding or 'Corrective action',
                'chapter': 'N/A',
                'value': 0,
                'status': 'fail',
                'finding_text': ca.finding or '',
                'note': '',
                'critical_value': 0,
            }
            detailed_questions.append(target)
        target.setdefault('corrective_action', []).append(car_row)

    if is_iatf_nc_mode:
        classification_counts = {
            'Major': 0,
            'Minor': 0,
            'Improvement': 0,
            'Strong Point': 0
        }
        
        for q in detailed_questions:
            classification = q.get('classification')
            if classification in classification_counts:
                classification_counts[classification] += 1
        
        total_fail = classification_counts.get('Major', 0)
        total_pass = classification_counts.get('Strong Point', 0)
        total_improve = classification_counts.get('Minor', 0) + classification_counts.get('Improvement', 0)
        total_not_audited = 0

    questionnaire_obj = audit.questionnaire
    report_profile = resolve_report_profile(
        questionnaire_name=getattr(questionnaire_obj, "name", None),
        audit_type_value=getattr(getattr(questionnaire_obj, "audit_type", None), "value", None),
        framework_code=getattr(getattr(questionnaire_obj, "framework", None), "code", None),
        framework_label=getattr(getattr(questionnaire_obj, "framework", None), "label", None),
        is_iatf_nc_mode=is_iatf_nc_mode,
    )
    
    audit_data = {
        "audit_number": audit.audit_number,
        "auditor": auditor_name,
        "auditees": auditees,
        "plant": audit.plant if audit.plant else "N/A",
        "sector": audit.sector if audit.sector else "N/A",
        "type": audit_type,
        "questionnaire_name": questionnaire_name,
        "status": audit.status if audit.status else "N/A",
        "is_iatf_nc_mode": is_iatf_nc_mode,
        "audit_date": format_datetime(audit.actual_start_date or audit.planned_start_date),
        "audit_end_date": format_datetime(audit.actual_end_date or audit.planned_end_date),
        "planned_start_date": format_datetime(audit.planned_start_date),
        "planned_end_date": format_datetime(audit.planned_end_date),
        "actual_start_date": format_datetime(audit.actual_start_date) if audit.actual_start_date else "N/A",
        "actual_end_date": format_datetime(audit.actual_end_date) if audit.actual_end_date else "N/A",
        "total_score": float(audit.total_score) if audit.total_score else 0.0,
        "result_class": audit.result_class,
        "potential_analysis_result_class": audit.potential_analysis_result_class,
        "total_pass": total_pass,
        "total_fail": total_fail,
        "total_improve": total_improve,
        "total_not_audited": total_not_audited,
        "strong_points": audit.strong_points if audit.strong_points else "No strong points documented.",
        "weak_points": audit.weak_points if audit.weak_points else "No weak points documented.",
        "detailed_questions": detailed_questions,
        "classification_counts": {
            'Major': sum(1 for q in detailed_questions if q.get('classification') == 'Major'),
            'Minor': sum(1 for q in detailed_questions if q.get('classification') == 'Minor'),
            'Improvement': sum(1 for q in detailed_questions if q.get('classification') == 'Improvement'),
            'Strong Point': sum(1 for q in detailed_questions if q.get('classification') == 'Strong Point'),
        } if is_iatf_nc_mode else None,
        "report_profile": report_profile,
    }

    # A P1-Potential-Analysis audit is either (a) a legacy standalone audit
    # planned directly against the P1 questionnaire (report_profile ==
    # "VDA_P1" via resolve_report_profile above, based on that questionnaire's
    # own name/framework) — in which case every answered question IS the
    # potential analysis — or (b) a merged VDA 6.3 audit that opted in to a
    # linked Potential Analysis questionnaire, in which case only answers
    # whose question belongs to that linked questionnaire count.
    linked_pa_questionnaire_id = getattr(questionnaire_obj, "potential_analysis_questionnaire_id", None)

    if report_profile == "VDA_P1":
        has_vda_sections = False
        p1_result = _build_p1_result(detailed_questions)
    elif linked_pa_questionnaire_id:
        has_vda_sections = any(
            question.get("questionnaire_id") == audit.questionnaire_id
            for question in detailed_questions
        )
        p1_result = _build_p1_result(
            detailed_questions,
            potential_analysis_questionnaire_id=linked_pa_questionnaire_id,
        )
    else:
        has_vda_sections = any(
            _question_element_code(question) in VDA_ELEMENTS
            for question in detailed_questions
        )
        p1_result = None

    if p1_result:
        audit_data["p1_result"] = p1_result
        audit_data.setdefault("vda_result", {})["p1_result"] = p1_result

    if has_vda_sections:
        questions_by_id = {
            q.id: q
            for q in (getattr(audit.questionnaire, "questions", None) or [])
            if getattr(q, "id", None) is not None
        }
        audit_data.setdefault("vda_result", {}).update(
            compute_vda_results(
                answers=audit.answers or [],
                questions_by_id=questions_by_id,
            )
        )

    if not is_iatf_nc_mode:
        if p1_result and has_vda_sections:
            audit_data["report_profile"] = "VDA_COMBINED"
        elif p1_result and not has_vda_sections:
            audit_data["report_profile"] = "VDA_P1"
        elif has_vda_sections:
            audit_data["report_profile"] = "VDA"
    
    return audit_data


@router.post("/{audit_id}/generate-report")
async def generate_audit_report_endpoint(
    audit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
):
    require_auditor_role(current_user)
    start_time = datetime.now()
    
    try:
        audit = db.query(Audit).filter(Audit.id == audit_id).first()
        if not audit:
            raise HTTPException(status_code=404, detail="Audit not found")
        
        # Check if regeneration
        old_sp_metadata = decode_sharepoint_url(audit.report_url) if audit.report_url else None
        is_regeneration = bool(old_sp_metadata)
        
        logger.info(f"Starting report generation for audit {audit_id} (regeneration: {is_regeneration})")
        
        # Build audit data
        audit_data = get_audit_data_for_report(audit_id, db)
        
        # Generate filename
        audit_number = (audit_data["audit_number"] or "N-A").replace("/", "_").replace(" ", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_type = "iatf_nc" if audit_data.get("is_iatf_nc_mode") else "audit"
        filename = f"{report_type}_report_{audit_number}_{timestamp}.pdf"
        
        # Generate locally (temp)
        output_path = REPORTS_DIR / filename
        logo_path_str = str(LOGO_PATH) if LOGO_PATH.exists() else None
        
        logger.info(f"Generating PDF for audit {audit_id}")
        report_path = generate_audit_report(
            audit_data=audit_data,
            output_path=str(output_path),
            logo_path=logo_path_str
        )
        report_path = Path(report_path)
        
        if not report_path.exists() or report_path.stat().st_size == 0:
            raise Exception("Report file was not created successfully")
        
        file_size = report_path.stat().st_size
        logger.info(f"PDF generated successfully: {file_size} bytes")
        
        #  Upload NEW file FIRST (before deleting old)
        plant_name = audit_data.get("plant") or "Unknown-Plant"
        logger.info(f"Uploading to SharePoint: plant={plant_name}, filename={filename}")
        
        upload_result = await sp_storage.upload_report_to_plant(
            plant_name=plant_name,
            pdf_path=report_path,
            filename=filename,
        )
        
        logger.info(f"Upload successful: {upload_result['file']['webUrl']}")
        
        # Only delete old file AFTER successful upload
        if is_regeneration and old_sp_metadata:
            try:
                logger.info(f"Deleting old SharePoint file: {old_sp_metadata['item_id']}")
                await sp_storage.delete_by_item_id(
                    old_sp_metadata["drive_id"],
                    old_sp_metadata["item_id"]
                )
                logger.info("Old report deleted successfully")
            except Exception as e:
                logger.warning(f"Could not delete old SharePoint file: {e}")
        
        # Update database in transaction
        try:
            audit.report_url = encode_sharepoint_url(
                drive_id=upload_result["drive_id"],
                item_id=upload_result["file"]["id"],
                web_url=upload_result["file"]["webUrl"],
                sp_path=upload_result["file"]["path"]
            )
            
            db.commit()
            generation_duration = (datetime.now() - start_time).total_seconds()
            logger.info(f"Database updated successfully (took {generation_duration:.2f}s)")
            
        except Exception as e:
            logger.error(f"Database commit failed: {e}")
            db.rollback()
            
            # Rollback - delete newly uploaded file
            try:
                logger.info("Rolling back - deleting newly uploaded file")
                await sp_storage.delete_by_item_id(
                    upload_result["drive_id"],
                    upload_result["file"]["id"]
                )
            except Exception as rollback_error:
                logger.error(f"Rollback deletion failed: {rollback_error}")
            
            raise HTTPException(status_code=500, detail=f"Database update failed: {str(e)}")
        
        # Clean up local temp file
        try:
            report_path.unlink(missing_ok=True)
            logger.info(f"Local temp file deleted: {report_path}")
        except Exception as e:
            logger.warning(f"Could not delete local temp file: {e}")
        
        total_duration = (datetime.now() - start_time).total_seconds()
        logger.info(f"Report generation complete for audit {audit_id} (total time: {total_duration:.2f}s)")
        
        # Return success with report ready
        return {
            "success": True,
            "message": "Report regenerated successfully" if is_regeneration else "Report generated successfully",
            "is_regeneration": is_regeneration,
            "report_ready": True,  
            "filename": filename,
            "sharepoint_url": upload_result["file"]["webUrl"],
            "generation_time_seconds": round(total_duration, 2)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating report for audit {audit_id}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating report: {str(e)}")


@router.get("/{audit_id}/download-report")
async def download_audit_report(
    audit_id: int,
    db: Session = Depends(get_db),
):
    """Download the generated audit report PDF from SharePoint"""
    audit = db.query(Audit).filter(Audit.id == audit_id).first()
    
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    
    sp_metadata = decode_sharepoint_url(audit.report_url)
    
    if not sp_metadata:
        raise HTTPException(
            status_code=404, 
            detail="Report not found in SharePoint. Please generate the report first."
        )
    
    try:
        sp_response = await sp_storage.download_content_stream(
            sp_metadata["drive_id"],
            sp_metadata["item_id"]
        )
        
        audit_number = audit.audit_number.replace("/", "_").replace(" ", "_")
        filename = f"audit_report_{audit_number}.pdf"
        
        async def stream_generator():
            try:
                async for chunk in sp_response.aiter_bytes(chunk_size=8192):
                    yield chunk
            finally:
                await sp_storage.close_stream(sp_response)
        
        return StreamingResponse(
            stream_generator(),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-cache",
            }
        )
        
    except Exception as e:
        logger.error(f"Error downloading from SharePoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error downloading report: {str(e)}")

@router.get("/{audit_id}/preview-pdf")
async def preview_audit_report_pdf(
    audit_id: int,
    db: Session = Depends(get_db),
):
    """Stream the PDF from SharePoint for in-browser preview"""
    audit = db.query(Audit).filter(Audit.id == audit_id).first()
    
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    
    sp_metadata = decode_sharepoint_url(audit.report_url)
    
    if not sp_metadata:
        raise HTTPException(
            status_code=404, 
            detail="Report not found in SharePoint. Please generate the report first."
        )
    
    try:
        sp_response = await sp_storage.download_content_stream(
            sp_metadata["drive_id"],
            sp_metadata["item_id"]
        )
        
        audit_number = audit.audit_number.replace("/", "_").replace(" ", "_")
        filename = f"audit_report_{audit_number}.pdf"
        
        async def stream_generator():
            try:
                async for chunk in sp_response.aiter_bytes(chunk_size=8192):
                    yield chunk
            finally:
                await sp_storage.close_stream(sp_response)
        
        return StreamingResponse(
            stream_generator(),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
                # Reports can be regenerated at the same URL. Do not let the
                # browser keep showing the previous PDF after regeneration.
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            }
        )
        
    except Exception as e:
        logger.error(f"Error streaming PDF from SharePoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error loading PDF preview: {str(e)}")


def _stamp_complete_report_banner(pdf_bytes: bytes) -> bytes:
    """Print an "internal" banner at the top of every page of the complete
    report, so it can't be mistaken for the auditee-facing one."""
    from io import BytesIO
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas as pdf_canvas

    banner = (
        "COMPLETE REPORT - INTERNAL - includes Silent Box findings marked "
        f"{SILENT_BOX_TAG}. Do not send to auditees."
    )
    reader = PdfReader(BytesIO(pdf_bytes))
    writer = PdfWriter()
    for page in reader.pages:
        width = float(page.mediabox.width)
        height = float(page.mediabox.height)
        overlay_buffer = BytesIO()
        overlay = pdf_canvas.Canvas(overlay_buffer, pagesize=(width, height))
        overlay.setFillColor(colors.HexColor("#b91c1c"))
        overlay.setFont("Helvetica-Bold", 8)
        overlay.drawCentredString(width / 2, height - 14, banner)
        overlay.save()
        overlay_buffer.seek(0)
        page.merge_page(PdfReader(overlay_buffer).pages[0])
        writer.add_page(page)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


@router.get("/{audit_id}/complete-report-pdf")
async def complete_audit_report_pdf(
    audit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
):
    """Internal "complete" report including Silent Box findings.

    Generated on demand and never stored on SharePoint or emailed, so the
    auditee-facing report (generate-report / preview-pdf / send-email) keeps
    hiding Silent Box findings. Limited to roles that can see Silent Box
    answers in the app.
    """
    if not can_view_silent_box(current_user):
        raise HTTPException(
            status_code=403,
            detail="You are not allowed to view Silent Box findings.",
        )

    audit_data = get_audit_data_for_report(audit_id, db, include_silent_box=True)
    audit_number = (audit_data["audit_number"] or "N-A").replace("/", "_").replace(" ", "_")
    output_path = REPORTS_DIR / f"complete_report_{audit_number}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.pdf"
    try:
        report_path = Path(
            generate_audit_report(
                audit_data=audit_data,
                output_path=str(output_path),
                logo_path=str(LOGO_PATH) if LOGO_PATH.exists() else None,
            )
        )
        pdf_bytes = _stamp_complete_report_banner(report_path.read_bytes())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating complete report for audit {audit_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Error generating complete report: {str(e)}")
    finally:
        output_path.unlink(missing_ok=True)

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="complete_audit_report_{audit_number}.pdf"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/{audit_id}/send-email")
async def send_audit_report_email(
    audit_id: int,
    payload: SendReportEmailRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
):
    """Send audit report via email to selected recipients"""
    require_auditor_role(current_user)
    audit = db.query(Audit).filter(Audit.id == audit_id).first()
    
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    
    sp_metadata = decode_sharepoint_url(audit.report_url)
    
    if not sp_metadata:
        raise HTTPException(
            status_code=404,
            detail="Report not found in SharePoint. Please generate the report first."
        )
    
    recipients = list(payload.recipients)
    cc_list = []
    
    if payload.include_auditor:
        # Lead auditor and optional second auditor are both CC'd.
        for auditor in (audit.auditor, audit.second_auditor):
            auditor_email = auditor.email if auditor else None
            if auditor_email and auditor_email not in recipients and auditor_email not in cc_list:
                cc_list.append(auditor_email)
    
    if not recipients and not cc_list:
        raise HTTPException(status_code=400, detail="No recipients specified")
    
    try:
        sp_response = await sp_storage.download_content_stream(
            sp_metadata["drive_id"],
            sp_metadata["item_id"]
        )
        
        audit_number_safe = audit.audit_number.replace("/", "_").replace(" ", "_")
        temp_filename = f"audit_report_{audit_number_safe}_{audit.plant}.pdf"
        temp_path = REPORTS_DIR / temp_filename
        
        with open(temp_path, "wb") as f:
            async for chunk in sp_response.aiter_bytes(chunk_size=8192):
                f.write(chunk)
        
        await sp_storage.close_stream(sp_response)
        
        audit_data = get_audit_data_for_report(audit_id, db)
        email_body = create_email_body(audit_data, payload.custom_message)
        subject = f"Audit Report - {audit.audit_number}"
        
        await send_email_with_attachment(
            recipients=recipients,
            subject=subject,
            body_html=email_body,
            attachment_path=str(temp_path),
            attachment_filename=temp_filename,
            cc=cc_list if cc_list else None
        )
        
        try:
            temp_path.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Could not delete temp email file: {e}")
        
        total_recipients = recipients + cc_list
        
        return {
            "success": True,
            "message": "Report sent successfully to recipient(s)",
            "sent_to": total_recipients,
            "sent_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error sending email: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")

@router.delete("/{audit_id}/report")
async def delete_audit_report(
    audit_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
):
    """Delete the generated report file from SharePoint"""
    require_auditor_role(current_user)
    audit = db.query(Audit).filter(Audit.id == audit_id).first()
    
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    
    sp_metadata = decode_sharepoint_url(audit.report_url)
    
    if not sp_metadata:
        raise HTTPException(status_code=404, detail="No report found to delete")
    
    try:
        await sp_storage.delete_by_item_id(
            sp_metadata["drive_id"],
            sp_metadata["item_id"]
        )
        
        audit.report_url = None
        db.commit()

        return {"success": True, "message": "Report deleted successfully from SharePoint"}

    except Exception as e:
        logger.error(f"Error deleting report from SharePoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting report: {str(e)}")


def _fetch_answers_and_questions_for_vda_merge(audit_id: int, db: Session):
    """Raw ORM answers + question lookup for one audit, shaped exactly as
    vda_scoring_service.compute_vda_results expects. Kept separate from
    get_audit_data_for_report (which returns pre-formatted dicts, not ORM
    objects) so several audits' raw answers can be concatenated and scored
    together as one virtual audit."""
    from sqlalchemy.orm import joinedload

    audit = (
        db.query(Audit)
        .options(
            joinedload(Audit.answers).joinedload(AuditAnswer.question),
            joinedload(Audit.questionnaire),
        )
        .filter(Audit.id == audit_id)
        .first()
    )
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    visible_answers = [a for a in (audit.answers or []) if not getattr(a, "silent_box", False)]
    questions = getattr(audit.questionnaire, "questions", None) or []
    questions_by_id = {q.id: q for q in questions if getattr(q, "id", None) is not None}
    return visible_answers, questions_by_id


@router.post("/consolidate-theme-report")
async def consolidate_theme_report(
    payload: ConsolidateThemeReportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(auth_service.get_current_user),
):
    """Merge several audits of the same plant + questionnaire into one PDF.

    VDA 6.3 audits read like a single VDA report: their raw answers are
    combined and re-scored as one virtual audit (same engine as a single
    audit), so the audit-result table, detailed evaluation matrix, and action
    plan reflect the true consolidated points. Every other report profile
    gets a findings report grouped by theme (see
    consolidation_report_service.generate_consolidated_findings_report)."""
    require_auditor_role(current_user)

    # De-dupe while preserving the order the auditor picked them in.
    audit_ids = list(dict.fromkeys(payload.audit_ids))
    if len(audit_ids) < 2:
        raise HTTPException(
            status_code=400,
            detail="Select at least two audits to consolidate.",
        )

    audits = db.query(Audit).filter(Audit.id.in_(audit_ids)).all()
    if len(audits) != len(audit_ids):
        raise HTTPException(status_code=404, detail="One or more audits were not found.")

    if len({a.plant for a in audits}) > 1 or len({a.questionnaire_id for a in audits}) > 1:
        raise HTTPException(
            status_code=400,
            detail="All selected audits must share the same plant and questionnaire.",
        )

    audits_data = [get_audit_data_for_report(audit_id, db) for audit_id in audit_ids]
    filename = f"consolidated_audit_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    # Only VDA 6.3 audits can be re-scored as one virtual audit (P2-P7
    # elements); every other profile (IATF NC, IATF PM, P1, standard) gets a
    # findings report where each audit keeps its own score.
    profiles = {(a.get("report_profile") or "STANDARD").upper() for a in audits_data}
    if not profiles <= VDA_CONSOLIDATION_PROFILES:
        report_profile = profiles.pop() if len(profiles) == 1 else "STANDARD"
        pdf_bytes = generate_consolidated_findings_report(
            audits_data=audits_data,
            findings=build_consolidated_findings(audits_data, report_profile),
            report_profile=report_profile,
        )
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    audits_meta = []
    action_plan_rows: List[dict] = []
    all_answers = []
    merged_questions_by_id: Dict[int, object] = {}

    for audit_id, audit_data in zip(audit_ids, audits_data):
        audits_meta.append(
            {
                "audit_number": audit_data["audit_number"],
                "plant": audit_data["plant"],
                "auditor": audit_data.get("auditor") or "N/A",
                "questionnaire_name": audit_data.get("questionnaire_name") or "N/A",
                "audit_date": audit_data["audit_date"],
                "total_score": audit_data.get("total_score", 0.0),
                "result_class": audit_data.get("result_class") or "n.e.",
                "strong_points": audit_data.get("strong_points"),
                "weak_points": audit_data.get("weak_points"),
                # Per-audit narrative fields, carried forward verbatim from
                # this audit's own report so they aren't merged/overwritten
                # by another audit's content (see get_audit_data_for_report).
                "summary": audit_data.get("summary"),
                "confirmation_date": audit_data.get("confirmation_date"),
                "effectiveness_date": audit_data.get("effectiveness_date"),
                # This audit's own Detailed Evaluation Matrix (per P2-P7
                # element), independent of the merged virtual-audit matrix,
                # so each source audit's ratings stay individually visible.
                "vda_result": audit_data.get("vda_result") or {},
            }
        )

        for question in audit_data["detailed_questions"]:
            action_plan_rows.append(
                {
                    "audit_number": audit_data["audit_number"],
                    "element": _question_element_code(question) or "Unclassified",
                    "question_code": question.get("question_code") or question.get("identifer") or "",
                    "chapter": question.get("chapter") or "N/A",
                    "finding_text": question.get("finding_text") or "",
                    "value": question.get("value"),
                    "critical_value": question.get("critical_value"),
                    "corrective_action": question.get("corrective_action") or [],
                }
            )

        answers, questions_by_id = _fetch_answers_and_questions_for_vda_merge(audit_id, db)
        all_answers.extend(answers)
        merged_questions_by_id.update(questions_by_id)

    if not action_plan_rows:
        raise HTTPException(
            status_code=404,
            detail="No findings were found across the selected audits.",
        )

    vda_result = compute_vda_results(answers=all_answers, questions_by_id=merged_questions_by_id)

    pdf_bytes = generate_consolidated_vda_report(
        audits_meta=audits_meta,
        vda_result=vda_result,
        action_plan_rows=action_plan_rows,
    )

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
