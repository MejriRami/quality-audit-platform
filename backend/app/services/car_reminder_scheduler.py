import asyncio
import json
import logging
import os
import time
from datetime import date
from collections import defaultdict
from sqlalchemy.orm import Session
from sqlalchemy import and_
from apscheduler.schedulers.background import BackgroundScheduler

from app.config.database import SessionLocal
from app.models.corrective_action import CorrectiveAction
from app.utils.send_car_email import (
    get_or_create_car_token,
    build_car_form_url,
    build_unavailability_url,
    build_auditee_portal_url,
)
from app.services.car_service import get_or_create_unavailability_form_token
from app.services.email_delivery_service import send_email_sync_tracked
from app.services.audit_planning.service import run_monthly_plan_job
from app.services.certification_expiry_service import run_certification_expiry_job
from app.utils.due_date import get_remaining_working_days

logger = logging.getLogger(__name__)

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
MAX_EMAILS_PER_BATCH = int(os.getenv("MAX_EMAILS_PER_BATCH", "50"))
BATCH_DELAY_SECONDS = int(os.getenv("BATCH_DELAY_SECONDS", "2"))
MAX_RETRIES = int(os.getenv("MAX_EMAIL_RETRIES", "3"))
RETRY_DELAY_SECONDS = 5


# ─────────────────────────────────────────────────────────────
# Existing reminder helpers (unchanged)
# ─────────────────────────────────────────────────────────────


def get_cars_due_in_days(db: Session, days: int) -> list[CorrectiveAction]:
    today = date.today()
    candidates = (
        db.query(CorrectiveAction)
        .filter(
            and_(
                CorrectiveAction.due_date != None,
                CorrectiveAction.due_date >= today,
                CorrectiveAction.status == "pending",
            )
        )
        .all()
    )
    matching: list[CorrectiveAction] = []
    for car in candidates:
        audit = car.audit
        if not audit or not audit.plant or not car.due_date:
            continue
        remaining_days = get_remaining_working_days(
            from_date=today,
            due_date=car.due_date,
            plant=str(audit.plant).lower(),
        )
        if remaining_days == days:
            matching.append(car)
    return matching


def group_cars_by_audit_auditee_and_due_date(cars: list[CorrectiveAction]) -> dict:
    """Group CARs sharing the same audit, auditee and due date into one email."""
    grouped = defaultdict(list)
    for car in cars:
        if car.auditee and car.auditee.email and car.audit:
            key = (car.audit_id, car.auditee.email, car.due_date)
            grouped[key].append(car)
        else:
            logger.warning(f"CAR ID {car.id} missing auditee email or audit - skipping")
    return grouped


def _parse_cc_emails(car: CorrectiveAction) -> list[str]:
    if not car.cc_emails:
        return []
    try:
        parsed = json.loads(car.cc_emails)
        if isinstance(parsed, list):
            return [str(e).strip().lower() for e in parsed if str(e).strip()]
    except Exception:
        pass
    return []


def determine_car_type(answer) -> str:
    if not answer:
        return "Observation"
    if answer.fail:
        return "Critical"
    if answer.improve:
        return "Improvement"
    return "Observation"


def build_reminder_email_html(
    auditee_name: str,
    audit_reference: str,
    cars: list[dict],
    unavailability_url: str,
    days_before: int,
    portal_url: str,
) -> str:
    if days_before == 1:
        urgency_color = "#dc3545"
        urgency_bg = "#f8d7da"
        urgency_border = "#dc3545"
        urgency_text_color = "#721c24"
        icon = "🚨"
        title = "URGENT: Corrective Actions Due Tomorrow"
        subtitle = "Immediate Action Required"
        message = "The following corrective actions are <strong style='color: #dc3545;'>due tomorrow</strong>. Please complete them immediately to avoid escalation."
        show_final_warning = True
        countdown_text = "TOMORROW"
        countdown_color = "#dc3545"
    elif days_before == 2:
        urgency_color = "#ffc107"
        urgency_bg = "#fff3cd"
        urgency_border = "#ffc107"
        urgency_text_color = "#856404"
        icon = "⏰"
        title = "Reminder: Corrective Actions Due Soon"
        subtitle = "Action Required Within 2 Days"
        message = f"The following corrective actions are <strong style='color: {urgency_color};'>due in 2 days</strong>. Please ensure they are completed before the deadline."
        show_final_warning = False
        countdown_text = "2 DAYS"
        countdown_color = "#ffc107"
    else:
        urgency_color = "#1976d2"
        urgency_bg = "#e3f2fd"
        urgency_border = "#64b5f6"
        urgency_text_color = "#0d47a1"
        icon = "📌"
        title = "Reminder: Corrective Actions Due Soon"
        subtitle = "Action Required Within 3 Working Days"
        message = "The following corrective actions are <strong style='color: #1976d2;'>due in 3 working days</strong>. Please prepare the actions and complete them before the deadline."
        show_final_warning = False
        countdown_text = "3 DAYS"
        countdown_color = "#1976d2"

    rows_html = ""
    for i, car in enumerate(cars, 1):
        type_colors = {
            "Critical": "#C62828",
            "Observation": "#F9A825",
            "Improvement": "#0277BD",
        }
        badge_color = type_colors.get(car["type"], "#F9A825")
        due_date_str = (
            car["due_date"].strftime("%d/%m/%Y") if car["due_date"] else "Not defined"
        )
        row_bg = "#f9f9f9" if i % 2 == 0 else "#ffffff"

        rows_html += f"""
        <tr style="background:{row_bg};">
            <td style="padding:15px 12px;border:1px solid #e0e0e0;text-align:center;font-weight:bold;color:#666;">#{i}</td>
            <td style="padding:15px 12px;border:1px solid #e0e0e0;text-align:center;">
                <span style="background:{badge_color};color:white;padding:6px 12px;border-radius:20px;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;">{car["type"]}</span>
            </td>
            <td style="padding:15px 12px;border:1px solid #e0e0e0;color:#333;line-height:1.5;">{car["question"]}</td>
            <td style="padding:15px 12px;border:1px solid #e0e0e0;color:#666;line-height:1.5;font-size:14px;">{car["finding"]}</td>
            <td style="padding:15px 12px;border:1px solid #e0e0e0;text-align:center;">
                <div style="background:{urgency_bg};color:{urgency_text_color};padding:8px 12px;border-radius:6px;font-weight:700;font-size:14px;border:1px solid {urgency_border};">{due_date_str}</div>
            </td>
            <td style="padding:15px 12px;border:1px solid #e0e0e0;text-align:center;">
                <a href="{car["form_url"]}" style="display:inline-block;background:{urgency_color};color:#ffffff;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:700;font-size:14px;">Complete Form</a>
            </td>
        </tr>
        """
    final_warning_html = ""
    if show_final_warning:
        final_warning_html = """
        <div style="background-color:#dc3545;border:3px solid #721c24;padding:25px;margin:25px 0;text-align:center;border-radius:12px;">
            <p style="margin:0;color:#ffffff;font-size:20px;font-weight:800;text-transform:uppercase;letter-spacing:1px;">FINAL REMINDER - ACTION REQUIRED TODAY</p>
            <p style="margin:10px 0 0 0;color:#ffffff;font-size:14px;">Failure to complete may result in escalation to management</p>
        </div>
        """

    return f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
    <body style="font-family:'Segoe UI',Arial,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);padding:40px 20px;margin:0;">
    <div style="max-width:950px;margin:auto;background:white;border-radius:16px;box-shadow:0 10px 40px rgba(0,0,0,0.2);overflow:hidden;">
    <div style="background:linear-gradient(135deg,#1B5E20 0%,#2E7D32 100%);padding:30px;text-align:center;">
        <img src="{FRONTEND_URL}/assets/logo-northwind-tunisia.jpg" alt="Northwind" style="max-height:70px;margin-bottom:15px;filter:brightness(0) invert(1);" />
        <h1 style="color:white;margin:0;font-size:24px;font-weight:300;letter-spacing:1px;">Quality Management System</h1>
    </div>
    <div style="background:{urgency_bg};border-left:6px solid {urgency_border};padding:25px 30px;border-bottom:1px solid {urgency_border};">
        <h2 style="color:{urgency_text_color};margin:0 0 8px 0;font-size:28px;font-weight:700;">{icon} {title}</h2>
        <p style="color:{urgency_text_color};margin:0;font-size:16px;font-weight:600;">{subtitle}</p>
    </div>
    <div style="padding:35px 30px;">
        <p style="font-size:16px;line-height:1.8;color:#333;margin:0 0 20px 0;">Dear <strong style="color:#1B5E20;">{auditee_name}</strong>,</p>
        <p style="font-size:16px;line-height:1.8;color:#555;margin:0 0 25px 0;">{message}</p>
        <div style="background:#f8f9fa;border-left:4px solid #1B5E20;padding:20px;margin:25px 0;border-radius:8px;">
            <p style="margin:0;font-size:15px;color:#333;line-height:1.6;">
                <strong style="color:#1B5E20;">📋 Audit Reference:</strong> {audit_reference}<br>
                <strong style="color:#1B5E20;">📧 Assigned To:</strong> {auditee_name}<br>
                <strong style="color:#1B5E20;">📊 Total Actions:</strong> {len(cars)} Corrective Action{"s" if len(cars) > 1 else ""}
            </p>
        </div>
        {final_warning_html}
        <h3 style="color:#1B5E20;font-size:20px;margin:30px 0 20px 0;">📋 Actions Required:</h3>
        <div style="overflow-x:auto;margin:20px 0;">
            <table style="width:100%;border-collapse:collapse;">
                <thead>
                    <tr style="background:linear-gradient(135deg,#1B5E20 0%,#2E7D32 100%);">
                        <th style="padding:15px 12px;color:white;font-weight:700;text-align:center;">#</th>
                        <th style="padding:15px 12px;color:white;font-weight:700;text-align:center;">Type</th>
                        <th style="padding:15px 12px;color:white;font-weight:700;text-align:left;">Question</th>
                        <th style="padding:15px 12px;color:white;font-weight:700;text-align:left;">Finding</th>
                        <th style="padding:15px 12px;color:white;font-weight:700;text-align:center;">Due Date</th>
                        <th style="padding:15px 12px;color:white;font-weight:700;text-align:center;">Action</th>
                    </tr>
                </thead>
                <tbody>{rows_html}</tbody>
            </table>
        </div>
        <div style="text-align:center;margin:35px 0;background:#e8f5e9;padding:30px;border-radius:12px;border:2px dashed #2E7D32;">
            <p style="margin:0 0 15px 0;font-weight:700;color:#333;font-size:16px;">🤖 Need help? See all your non-conformities and get AI-assisted guidance.</p>
            <a href="{portal_url}" style="display:inline-block;background:#1B5E20;color:#ffffff;padding:15px 35px;border-radius:10px;text-decoration:none;font-weight:700;font-size:15px;">🔑 Go to My Portal &amp; AI Assistant</a>
        </div>
        <div style="text-align:center;margin:35px 0;background:#f8f9fa;padding:30px;border-radius:12px;border:2px dashed #6c757d;">
            <p style="margin:0 0 15px 0;font-weight:700;color:#333;font-size:16px;">🏖️ Will you be absent or on leave during this period?</p>
            <a href="{unavailability_url}" style="display:inline-block;background:#6c757d;color:#ffffff;padding:15px 35px;border-radius:10px;text-decoration:none;font-weight:700;font-size:15px;">📅 Declare Leave/Absence</a>
        </div>
        <div style="background:#fff3cd;border-left:4px solid #ffc107;padding:20px;margin:30px 0;border-radius:8px;">
            <p style="margin:0;color:#856404;line-height:1.6;">
                <strong style="font-size:16px;">Important Information:</strong><br><br>
                • Each corrective action has its own dedicated form<br>
                • Click the "Complete Form" button for each action individually<br>
                • All actions must be completed before the deadline<br>
                • Late submissions may result in management escalation
            </p>
        </div>
        <p style="margin:30px 0 10px 0;font-size:16px;color:#333;">Thank you for your prompt attention to these matters.</p>
        <p style="margin:10px 0 0 0;font-size:16px;color:#333;">Best regards,<br/><strong style="color:#1B5E20;">Quality Team – Northwind</strong></p>
    </div>
    <div style="background:#f8f9fa;padding:20px 30px;text-align:center;border-top:1px solid #e0e0e0;">
        <p style="margin:0;font-size:12px;color:#666;">This is an automated notification from the Northwind Quality Management System.</p>
    </div>
    </div></body></html>"""


def send_email_sync(
    subject: str,
    recipients: list[str],
    body_html: str,
    cc: list[str] | None = None,
    max_retries: int = MAX_RETRIES,
    db: Session | None = None,
    context: str | None = None,
    sender_email: str | None = None,
    sender_name: str | None = None,
    reply_to: str | None = None,
) -> bool:
    return send_email_sync_tracked(
        subject=subject,
        recipients=recipients,
        body_html=body_html,
        cc=cc,
        db=db,
        context=context or "car_reminder",
        max_retries=max_retries,
        retry_delay_seconds=RETRY_DELAY_SECONDS,
        sender_email=sender_email,
        sender_name=sender_name,
        reply_to=reply_to,
    )


def send_grouped_car_reminder(
    auditee_email: str, cars: list[CorrectiveAction], days_before: int, db: Session
) -> bool:
    try:
        if not cars:
            return False
        audit = cars[0].audit
        if not audit:
            logger.error("Audit not found for CARs")
            return False

        auditee_name = auditee_email.split("@")[0].replace(".", " ").title()
        cars_data = []

        for car in cars:
            try:
                token = get_or_create_car_token(db, car)
                form_url = build_car_form_url(token)
                question_text = "N/A"
                finding_text = car.finding or "N/A"
                car_type = "Observation"
                if car.answer:
                    if car.answer.question:
                        question_text = car.answer.question.description or "N/A"
                    finding_text = car.finding or car.answer.finding_text or "N/A"
                    car_type = determine_car_type(car.answer)
                cars_data.append(
                    {
                        "type": car_type,
                        "question": question_text,
                        "finding": finding_text,
                        "reason": car.reason_why or "N/A",
                        "due_date": car.due_date,
                        "form_url": form_url,
                    }
                )
            except Exception as e:
                logger.error(f"❌ Error preparing CAR {car.id}: {str(e)}")
                continue

        if not cars_data:
            logger.error("No valid CAR data to send")
            return False

        unavailability_token = get_or_create_unavailability_form_token(
            db=db,
            audit_id=audit.id,
            email=auditee_email,
        )
        unavailability_url = build_unavailability_url(unavailability_token)

        icon = "🚨" if days_before == 1 else "⚠️"
        urgency_prefix = "URGENT - " if days_before == 1 else ""
        car_count = len(cars_data)
        subject = (
            f"{icon} {urgency_prefix}{car_count} Corrective Action{'s' if car_count > 1 else ''} "
            f"- Due in {days_before} Working Day{'s' if days_before > 1 else ''} "
            f"(Audit {audit.audit_number})"
        )

        body_html = build_reminder_email_html(
            auditee_name=auditee_name,
            audit_reference=audit.audit_number,
            cars=cars_data,
            unavailability_url=unavailability_url,
            days_before=days_before,
            portal_url=build_auditee_portal_url(),
        )

        merged_cc: list[str] = []
        for car in cars:
            for cc_email in _parse_cc_emails(car):
                if cc_email not in merged_cc:
                    merged_cc.append(cc_email)

        success = send_email_sync(
            subject=subject,
            recipients=[auditee_email],
            body_html=body_html,
            cc=merged_cc or None,
            db=db,
            context="car_reminder",
            sender_email=getattr(getattr(audit, "auditor", None), "email", None),
            sender_name=getattr(getattr(audit, "auditor", None), "email", None),
            reply_to=getattr(getattr(audit, "auditor", None), "email", None),
        )

        if success:
            logger.info(
                f"✅ {days_before}-day reminder sent: {car_count} CAR(s) for audit {audit.audit_number} to {auditee_email}"
            )
        else:
            logger.error(
                f"❌ Failed to send {days_before}-day reminder for audit {audit.audit_number} to {auditee_email}"
            )

        return success

    except Exception as e:
        logger.error(f"❌ Error in send_grouped_car_reminder: {str(e)}", exc_info=True)
        return False


def check_and_send_reminders(days_before: int):
    logger.info(f"🔍 Starting CAR {days_before}-working-day reminder check...")
    start_time = time.time()
    db = None

    summary = {
        "days_before": days_before,
        "cars_due": 0,
        "groups": 0,
        "emails_sent": 0,
        "emails_failed": 0,
        "cars_in_sent_emails": 0,
        "elapsed_seconds": 0.0,
    }

    try:
        db = SessionLocal()
        cars_due_soon = get_cars_due_in_days(db, days_before)
        summary["cars_due"] = len(cars_due_soon)
        if not cars_due_soon:
            logger.info(f"✅ No corrective actions due in {days_before} working day(s)")
            summary["elapsed_seconds"] = round(time.time() - start_time, 2)
            return summary

        logger.info(
            f"📧 Found {len(cars_due_soon)} corrective action(s) due in {days_before} working day(s)"
        )
        grouped_cars = group_cars_by_audit_auditee_and_due_date(cars_due_soon)
        total_groups = len(grouped_cars)
        summary["groups"] = total_groups
        logger.info(f"📨 Grouped into {total_groups} email(s) to send")

        success_count = 0
        fail_count = 0
        total_cars_sent = 0
        batch_count = 0

        for i, ((audit_id, auditee_email, _due_date), cars) in enumerate(grouped_cars.items(), 1):
            try:
                result = send_grouped_car_reminder(
                    auditee_email=auditee_email,
                    cars=cars,
                    days_before=days_before,
                    db=db,
                )
                if result:
                    success_count += 1
                    total_cars_sent += len(cars)
                else:
                    fail_count += 1

                if i % MAX_EMAILS_PER_BATCH == 0 and i < total_groups:
                    batch_count += 1
                    logger.info(
                        f"📦 Batch {batch_count} completed ({i}/{total_groups}). Pausing {BATCH_DELAY_SECONDS}s..."
                    )
                    time.sleep(BATCH_DELAY_SECONDS)

            except Exception as e:
                fail_count += 1
                logger.error(
                    f"❌ Error sending reminder for audit {audit_id} to {auditee_email}: {str(e)}",
                    exc_info=True,
                )

        elapsed_time = time.time() - start_time
        logger.info(
            f"✅ {days_before}-day reminder check completed in {elapsed_time:.2f}s - "
            f"Emails sent: {success_count}/{total_groups}, Failed: {fail_count}, Total CARs: {total_cars_sent}"
        )
        summary["emails_sent"] = success_count
        summary["emails_failed"] = fail_count
        summary["cars_in_sent_emails"] = total_cars_sent
        summary["elapsed_seconds"] = round(elapsed_time, 2)

    except Exception as e:
        logger.error(
            f"❌ Critical error in check_and_send_reminders ({days_before} days): {str(e)}",
            exc_info=True,
        )
        summary["elapsed_seconds"] = round(time.time() - start_time, 2)
    finally:
        if db:
            try:
                db.close()
            except Exception as e:
                logger.error(f"Error closing database session: {str(e)}")
    return summary


def check_2_day_reminders():
    check_and_send_reminders(2)


def check_3_day_reminders():
    check_and_send_reminders(3)


def check_1_day_reminders():
    check_and_send_reminders(1)


# ─────────────────────────────────────────────────────────────
# ✅ NEW: Overdue CAR followup job (runs process_car_followups)
# ─────────────────────────────────────────────────────────────


def run_car_followups():
    """
    Synchronous wrapper to run the async process_car_followups()
    inside the APScheduler background thread.
    """
    from app.services.car_escalation_service import process_car_followups

    logger.info("🔍 Starting overdue CAR followup check...")
    db = None
    try:
        db = SessionLocal()
        result = asyncio.run(process_car_followups(db))
        logger.info(
            f"✅ CAR followup check completed — "
            f"open_cars_checked={result['open_cars_checked']}, "
            f"auditee_reminders={result['auditee_reminders_sent']}, "
            f"plant_manager_emails={result['plant_manager_emails_sent']}, "
            f"group_vp_emails={result['group_vp_emails_sent']}"
        )
    except Exception as e:
        logger.error(f"❌ Critical error in run_car_followups: {str(e)}", exc_info=True)
    finally:
        if db:
            try:
                db.close()
            except Exception as e:
                logger.error(f"Error closing database session: {str(e)}")


def run_avo_directory_sync():
    """
    Synchronous wrapper for the Northwind directory sync job (nightly). Owns its
    own DB session/lifecycle internally, same as sync_avo_directory's default
    behavior when called without one.
    """
    from app.services.org_member_directory import sync_avo_directory

    logger.info("🔍 Starting Northwind directory sync...")
    try:
        result = sync_avo_directory()
        if result.get("success"):
            logger.info(
                f"✅ Northwind directory sync completed — "
                f"fetched={result['fetched']}, upserted={result['upserted']}, "
                f"deactivated={result['deactivated']}"
            )
        else:
            logger.error(
                f"❌ Northwind directory sync failed (consecutive_failures="
                f"{result.get('consecutive_failures')}): {result.get('error')}"
            )
    except Exception as e:
        logger.error(f"❌ Critical error in run_avo_directory_sync: {str(e)}", exc_info=True)


def run_immediate_action_followups():
    """
    Synchronous wrapper to run immediate-action followups.
    """
    from app.services.car_escalation_service import process_immediate_action_followups

    logger.info("🔍 Starting immediate-action CAR followup check...")
    db = None
    try:
        db = SessionLocal()
        result = asyncio.run(process_immediate_action_followups(db))
        logger.info(
            f"✅ Immediate-action followup completed — "
            f"open_cars_checked={result['open_cars_checked']}, "
            f"immediate_12h_warnings={result['immediate_12h_warnings_sent']}, "
            f"immediate_24h_reminders={result['immediate_24h_reminders_sent']}, "
            f"immediate_48h_escalations={result['immediate_48h_escalations_sent']}"
        )
    except Exception as e:
        logger.error(
            f"❌ Critical error in run_immediate_action_followups: {str(e)}",
            exc_info=True,
        )
    finally:
        if db:
            try:
                db.close()
            except Exception as e:
                logger.error(f"Error closing database session: {str(e)}")


# ─────────────────────────────────────────────────────────────
# Scheduler setup
# ─────────────────────────────────────────────────────────────


def start_scheduler():
    """Initialize and start the APScheduler for CAR reminders and followups."""
    scheduler = BackgroundScheduler(
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300}
    )

    scheduler.add_job(
        check_3_day_reminders,
        "cron",
        hour=9,
        minute=15,
        id="car_reminder_3days",
        replace_existing=True,
        name="CAR 3-Day Reminders",
    )
    logger.info("✅ Scheduled: 3-day reminders at 9:00 AM daily")

    # 2-day reminders — 9:00 AM daily
    scheduler.add_job(
        check_2_day_reminders,
        "cron",
        hour=9,
        minute=15,
        id="car_reminder_2days",
        replace_existing=True,
        name="CAR 2-Day Reminders",
    )
    logger.info("✅ Scheduled: 2-day reminders at 9:00 AM daily")

    # 1-day reminders — 9:00 AM daily
    scheduler.add_job(
        check_1_day_reminders,
        "cron",
        hour=9,
        minute=15,
        id="car_reminder_1day",
        replace_existing=True,
        name="CAR 1-Day Reminders",
    )
    logger.info("✅ Scheduled: 1-day reminders at 9:00 AM daily")

    # ✅ Overdue CAR followups (day 9 / 11 / 15 escalations) — 9:05 AM daily
    # Runs 5 minutes after reminders to avoid DB contention
    scheduler.add_job(
        run_car_followups,
        "cron",
        hour=9,
        minute=15,
        id="car_followups",
        replace_existing=True,
        name="CAR Overdue Followups",
    )
    logger.info("✅ Scheduled: overdue CAR followups at 9:05 AM daily")

    # Immediate-action CARs run on a 24h/48h SLA, not a day-granularity one, so
    # this needs to poll far more often than the once-daily jobs above -
    # otherwise the 12h warning and the overdue notices can land many hours
    # late (up to a full day late, previously).
    scheduler.add_job(
        run_immediate_action_followups,
        "interval",
        minutes=30,
        id="car_immediate_action_followups",
        replace_existing=True,
        name="CAR Immediate Action Followups",
    )
    logger.info("✅ Scheduled: immediate-action followups every 30 minutes")

    # Northwind directory sync — nightly, at a quiet hour distinct from the 9:15
    # reminder/escalation batch above. Low volume (~400 people with an
    # email), so a full re-pull each run is cheap; no incremental sync
    # needed.
    scheduler.add_job(
        run_avo_directory_sync,
        "cron",
        hour=2,
        minute=0,
        id="org_directory_sync",
        replace_existing=True,
        name="Northwind Directory Sync",
    )
    logger.info("✅ Scheduled: Northwind directory sync at 2:00 AM daily")

    # Monthly audit plan - drafts the current month's plan on the 1st, once
    # last month's complaints/metrics are complete. After the 2:00 directory
    # sync so auditee lookups see fresh role data.
    scheduler.add_job(
        run_monthly_plan_job,
        "cron",
        day=1,
        hour=3,
        minute=0,
        id="audit_monthly_plan",
        replace_existing=True,
        name="Monthly Audit Plan",
    )
    logger.info("✅ Scheduled: monthly audit plan at 3:00 AM on the 1st")

    # Expired certificates - asks the quality manager for the renewed one.
    # Only sends when CERTIFICATION_EXPIRY_EMAILS_ENABLED is true.
    scheduler.add_job(
        run_certification_expiry_job,
        "cron",
        hour=9,
        minute=30,
        id="certification_expiry",
        replace_existing=True,
        name="Expired Certificate Notifications",
    )
    logger.info("✅ Scheduled: expired certificate notifications at 9:30 AM daily")

    scheduler.start()
    logger.info("✅ CAR reminder scheduler started successfully")

    for job in scheduler.get_jobs():
        logger.info(f"📅 {job.name}: Next run at {job.next_run_time}")

    return scheduler
