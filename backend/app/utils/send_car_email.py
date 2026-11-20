import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.correctiveActionsAccessToken import CorrectiveActionAccessToken
from app.models.corrective_action import CorrectiveAction
from app.services.email_delivery_service import (
    send_email_async_tracked,
    send_email_sync_tracked,
)

from dotenv import load_dotenv
load_dotenv()
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASSWORD")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
# How long a CAR access link stays valid. Configurable via env; defaults to 90 days.
CAR_TOKEN_TTL_DAYS = int(os.getenv("CAR_TOKEN_TTL_DAYS", "90"))


async def send_email(
    subject: str,
    recipients: list[str],
    body_html: str,
    cc: list[str] | None = None,
    db: Session | None = None,
    context: str | None = None,
    max_retries: int | None = None,
    sender_email: str | None = None,
    sender_name: str | None = None,
    reply_to: str | None = None,
):
    """Send email via SMTP."""
    return await send_email_async_tracked(
        subject=subject,
        recipients=recipients,
        body_html=body_html,
        cc=cc,
        db=db,
        context=context,
        max_retries=max_retries,
        sender_email=sender_email,
        sender_name=sender_name,
        reply_to=reply_to,
    )

async def send_email_with_attachment(
    recipients: List[str],
    subject: str,
    body_html: str,
    attachment_path: str,
    attachment_filename: str,
    cc: Optional[List[str]] = None,
    db: Session | None = None,
    context: str | None = None,
    max_retries: int | None = None,
    sender_email: str | None = None,
    sender_name: str | None = None,
    reply_to: str | None = None,
):
    """
    Extended version of send_email that supports PDF attachments
    
    Args:
        recipients: List of recipient email addresses
        subject: Email subject
        body_html: HTML body content
        attachment_path: Path to the PDF file
        attachment_filename: Name for the attachment
        cc: Optional list of CC recipients
    """
    ok = send_email_sync_tracked(
        subject=subject,
        recipients=recipients,
        body_html=body_html,
        cc=cc,
        db=db,
        context=context,
        max_retries=max_retries,
        attachment_path=attachment_path,
        attachment_filename=attachment_filename,
        sender_email=sender_email,
        sender_name=sender_name,
        reply_to=reply_to,
    )
    if not ok:
        raise Exception("Error sending email")
    return {"status": "Email sent successfully!"}
    
    
def get_or_create_car_token(db: Session, car: CorrectiveAction) -> str:
    """
    Get existing non-expired token for a CAR, or create a new one if none exists.
    Tokens are reusable until expiration for CAR form access.
    """
    now = datetime.now(timezone.utc)
    # Reuse an existing non-expired token when available.
    existing_token = db.query(CorrectiveActionAccessToken).filter(
        CorrectiveActionAccessToken.corrective_action_id == car.id,
        CorrectiveActionAccessToken.expires_at > now
    ).first()

    if existing_token:
        return existing_token.token

    # No valid token found, create a new one
    token_str = secrets.token_urlsafe(48)
    token = CorrectiveActionAccessToken(
        corrective_action_id=car.id,
        token=token_str,
        expires_at=now + timedelta(days=CAR_TOKEN_TTL_DAYS),
        used=False
    )
    db.add(token)
    db.commit()
    
    return token_str


# Backward compatibility - keep the old function name
def generate_car_token(db: Session, car: CorrectiveAction) -> str:
    """
    Generate or reuse a token for a CAR.
    This function now reuses existing tokens instead of always creating new ones.
    """
    return get_or_create_car_token(db, car)


def build_car_form_url(token: str) -> str:
    """Build complete CAR form URL with token."""
    return f"{FRONTEND_URL}/car-access?token={token}"


def build_unavailability_url(token: str) -> str:
    """Build unavailability declaration URL with token."""
    return f"{FRONTEND_URL}/audit-unavailability?token={token}"


def build_auditee_portal_url() -> str:
    """Build the auditee portal URL (plant + email are entered on the page)."""
    return f"{FRONTEND_URL}/auditee-portal"


def _section_form_url(form_url: str, section: str) -> str:
    """Append a `section` deep-link param so the button jumps straight to
    that part of the combined immediate/corrective form instead of the top."""
    separator = "&" if "?" in form_url else "?"
    return f"{form_url}{separator}section={section}"


def _build_car_row_html(
    *, badge_color: str, type_label: str, sub_badge: str, question: str,
    finding: str, reason: str, due_date_str: str, due_cell_style: str,
    form_url: str, button_label: str,
) -> str:
    return f"""
    <tr>
        <td style="padding:12px;border:1px solid #ddd;text-align:center;">
            <span style="
                background:{badge_color};
                color:white;
                padding:4px 8px;
                border-radius:4px;
                font-size:12px;
                font-weight:600;
            ">
                {type_label}
            </span>
            {sub_badge}
        </td>
        <td style="padding:12px;border:1px solid #ddd;">{question}</td>
        <td style="padding:12px;border:1px solid #ddd;">{finding}</td>
        <td style="padding:12px;border:1px solid #ddd;">{reason}</td>
        <td style="padding:12px;border:1px solid #ddd;text-align:center;{due_cell_style}">{due_date_str}</td>
        <td style="padding:14px;border:1px solid #e0e0e0;text-align:center;white-space:nowrap;">
            <a href="{form_url}"
               style="
                   display:inline-block;
                   background:#1976D2;
                   color:#ffffff;
                   padding:10px 18px;
                   border-radius:6px;
                   text-decoration:none;
                   font-weight:600;
                   font-size:14px;
               ">
               {button_label}
            </a>
        </td>
    </tr>
    """


def _build_car_rows_html(cars: list[dict]) -> str:
    rows_html = ""

    for car in cars:
        badge_color = "#C62828" if car["type"] == "Critical" else "#F9A825"
        is_immediate = bool(car.get("immediate_action_required"))
        submission_due_at = car.get("submission_due_at")

        if not is_immediate:
            due_date_str = car["due_date"].strftime("%d/%m/%Y") if car["due_date"] else "Not defined"
            rows_html += _build_car_row_html(
                badge_color=badge_color, type_label=car["type"], sub_badge="",
                question=car["question"], finding=car["finding"], reason=car["reason"],
                due_date_str=due_date_str, due_cell_style="",
                form_url=car["form_url"], button_label="Fill Form",
            )
            continue

        # Immediate-action finding -- two separate rows, two separate deep
        # links into the same combined form, so each obligation and its own
        # deadline is a distinct entry point instead of one link that opens
        # both sections at once.
        immediate_due_str = (
            submission_due_at.strftime("%d/%m/%Y %H:%M") if submission_due_at else "Not defined"
        )
        rows_html += _build_car_row_html(
            badge_color="#DC3545", type_label="IMMEDIATE ACTION",
            sub_badge="""<br/><span style="
                background:#7A1E1E;color:white;padding:3px 7px;border-radius:4px;
                font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;
                display:inline-block;margin-top:4px;
            ">⚡ Due in 24h</span>""",
            question=car["question"], finding=car["finding"], reason=car["reason"],
            due_date_str=immediate_due_str,
            due_cell_style="background:#FDECEA;color:#7A1E1E;font-weight:700;border:1px solid #DC3545;",
            form_url=_section_form_url(car["form_url"], "immediate"),
            button_label="Fill Immediate Action",
        )

        corrective_due_str = car["due_date"].strftime("%d/%m/%Y") if car["due_date"] else "Not defined"
        rows_html += _build_car_row_html(
            badge_color=badge_color, type_label="CORRECTIVE ACTION", sub_badge="",
            question=car["question"], finding=car["finding"], reason=car["reason"],
            due_date_str=corrective_due_str, due_cell_style="",
            form_url=_section_form_url(car["form_url"], "corrective"),
            button_label="Fill Corrective Action",
        )

    return rows_html


def _build_immediate_action_banner(cars: list[dict]) -> str:
    """Standalone warning banner shown above the CAR table when at least one
    CAR in the batch is flagged as requiring immediate action (24h/48h SLA
    instead of the standard due date)."""
    if not any(car.get("immediate_action_required") for car in cars):
        return ""
    return """
    <div style="background:#FDECEA;border:2px solid #DC3545;padding:16px 18px;margin:18px 0;border-radius:8px;">
        <p style="margin:0;color:#7A1E1E;font-weight:700;font-size:15px;">
            ⚡ One or more corrective actions below require IMMEDIATE ACTION.
        </p>
        <p style="margin:6px 0 0 0;color:#7A1E1E;font-size:13px;">
            These must be submitted within 24 hours of this notification. Failure to submit in time
            will trigger an escalation to your Plant Manager after 48 hours.
        </p>
    </div>
    """


def build_car_table_section_html(cars: list[dict]) -> str:
    """
    Build the CAR table as a standalone HTML fragment (no page wrapper, no greeting).
    Meant to be embedded into another email body, e.g. the combined audit report email.
    """
    rows_html = _build_car_rows_html(cars)
    immediate_banner = _build_immediate_action_banner(cars)

    return f"""
    <div style="margin-top:25px;">
        <h3 style="color:#1B5E20;">Corrective Actions to Address</h3>
        <p>Following this audit, corrective actions have been identified. Please complete
        <strong>each corrective action form</strong> before the indicated deadline.</p>
        {immediate_banner}
        <div style="overflow-x:auto;">
            <table style="width:100%;border-collapse:collapse;margin-top:10px;min-width:600px;">
                <thead>
                    <tr style="background:#eeeeee;">
                        <th style="padding:10px;border:1px solid #ddd;">Type</th>
                        <th style="padding:10px;border:1px solid #ddd;">Question</th>
                        <th style="padding:10px;border:1px solid #ddd;">Finding</th>
                        <th style="padding:10px;border:1px solid #ddd;">Issue</th>
                        <th style="padding:10px;border:1px solid #ddd;">Due Date</th>
                        <th style="padding:10px;border:1px solid #ddd;text-align:center;">Action</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>
        <div style="background:#fff3cd;border-left:4px solid #ffc107;padding:15px;margin-top:20px;border-radius:4px;">
            <p style="margin:0;">
                <strong>Important:</strong><br/>
                Each corrective action has its own form.<br/>
                Please handle them individually.
            </p>
        </div>
    </div>
    """


def build_combined_report_email_body(
    auditee_name: str,
    audit_reference: str,
    plant: str,
    cars: list[dict],
    unavailability_url: str,
) -> str:
    """
    Build the HTML body for the auto-sent audit report email: the executed
    audit's summary, the generated PDF is attached separately, and (when the
    audit produced CARs) the CAR table plus the leave-declaration and portal
    buttons, same as the standalone CAR notification email.
    """
    car_section = build_car_table_section_html(cars) if cars else ""

    leave_block = ""
    if cars:
        leave_block = f"""
        <div style="text-align:center;margin-top:25px;background:#f8f9fa;padding:20px;border-radius:6px;">
            <p style="margin-bottom:10px;font-weight:600;color:#333;">
                Will you be absent or on leave during this period?
            </p>
            <a href="{unavailability_url}"
               style="
                   display:inline-block;
                   background:#6c757d;
                   color:#ffffff;
                   padding:12px 22px;
                   border-radius:6px;
                   text-decoration:none;
                   font-weight:600;
                   font-size:14px;
               ">
               Declare Leave
            </a>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family:Arial, sans-serif;background:#f4f6f8;padding:20px;margin:0;">
        <div style="max-width:900px;margin:auto;background:white;padding:30px;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1);">

            <div style="text-align:center;margin-bottom:20px;">
                <img src="https://your-app.azurewebsites.net/assets/northwind-CfOjGbwW.png"
                     alt="Northwind"
                     style="max-height:60px;" />
            </div>

            <h2 style="color:#1B5E20;margin-top:0;">
                Audit Report - Northwind
            </h2>

            <p>Hello <strong>{auditee_name}</strong>,</p>

            <p>
                The audit <strong>{audit_reference}</strong> ({plant or "N/A"}) has been
                executed and the report is attached to this email.
            </p>

            {car_section}
            {leave_block}

            <div style="text-align:center;margin-top:30px;padding-top:25px;border-top:1px solid #eeeeee;">
                <a href="{build_auditee_portal_url()}"
                   style="
                       display:inline-block;
                       background:#1B5E20;
                       color:#ffffff;
                       padding:12px 22px;
                       border-radius:6px;
                       text-decoration:none;
                       font-weight:600;
                       font-size:14px;
                   ">
                   Go to My Portal
                </a>
                <p style="margin-top:12px;color:#666;font-size:13px;">
                    Prefer one place for everything? Open the portal to view and complete
                    all your corrective actions using your Northwind email.
                </p>
            </div>

            <p style="margin-top:20px;">
                Best regards,<br/>
                <strong>Quality Team - Northwind</strong>
            </p>
        </div>
    </body>
    </html>
    """


def build_car_email_body(
    auditee_name: str,
    audit_reference: str,
    cars: list[dict],
    unavailability_url: str,
) -> str:
    """
    Build HTML email body for CAR notifications.
    This is the standard template used when creating CARs (initial notification).
    """
    rows_html = _build_car_rows_html(cars)
    immediate_banner = _build_immediate_action_banner(cars)

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
    </head>
    <body style="font-family:Arial, sans-serif;background:#f4f6f8;padding:20px;margin:0;">
        <div style="max-width:900px;margin:auto;background:white;padding:30px;border-radius:8px;box-shadow:0 2px 4px rgba(0,0,0,0.1);">
            
            <div style="text-align:center;margin-bottom:20px;">
                <img src="https://your-app.azurewebsites.net/assets/northwind-CfOjGbwW.png"
                     alt="Northwind"
                     style="max-height:60px;" />
            </div>

            <h2 style="color:#1B5E20;margin-top:0;">
                Corrective Actions Notification - Northwind
            </h2>

            <p>Hello <strong>{auditee_name}</strong>,</p>

            <p>
                Following audit <strong>{audit_reference}</strong>, 
                corrective actions have been identified.
            </p>

            <p>
                Please complete <strong>each corrective action form</strong>
                before the indicated deadline.
            </p>

            {immediate_banner}

            <div style="overflow-x:auto;">
                <table style="width:100%;border-collapse:collapse;margin-top:20px;min-width:600px;">
                    <thead>
                        <tr style="background:#eeeeee;">
                            <th style="padding:10px;border:1px solid #ddd;">Type</th>
                            <th style="padding:10px;border:1px solid #ddd;">Question</th>
                            <th style="padding:10px;border:1px solid #ddd;">Finding</th>
                            <th style="padding:10px;border:1px solid #ddd;">Issue</th>
                            <th style="padding:10px;border:1px solid #ddd;">Due Date</th>
                            <th style="padding:10px;border:1px solid #ddd;text-align:center;">Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
            </div>

            <div style="text-align:center;margin-top:25px;background:#f8f9fa;padding:20px;border-radius:6px;">
                <p style="margin-bottom:10px;font-weight:600;color:#333;">
                    Will you be absent or on leave during this period?
                </p>
                <a href="{unavailability_url}"
                   style="
                       display:inline-block;
                       background:#6c757d;
                       color:#ffffff;
                       padding:12px 22px;
                       border-radius:6px;
                       text-decoration:none;
                       font-weight:600;
                       font-size:14px;
                   ">
                   Declare Leave
                </a>
            </div>

            <div style="background:#fff3cd;border-left:4px solid #ffc107;padding:15px;margin-top:30px;border-radius:4px;">
                <p style="margin:0;">
                    <strong>Important:</strong><br/>
                    Each corrective action has its own form.<br/>
                    Please handle them individually.
                </p>
            </div>

            <div style="text-align:center;margin-top:30px;padding-top:25px;border-top:1px solid #eeeeee;">
                <a href="{build_auditee_portal_url()}"
                   style="
                       display:inline-block;
                       background:#1B5E20;
                       color:#ffffff;
                       padding:12px 22px;
                       border-radius:6px;
                       text-decoration:none;
                       font-weight:600;
                       font-size:14px;
                   ">
                   Go to My Portal
                </a>
                <p style="margin-top:12px;color:#666;font-size:13px;">
                    Prefer one place for everything? Open the portal to view and complete
                    all your corrective actions using your Northwind email.
                </p>
            </div>

            <p style="margin-top:20px;">
                Best regards,<br/>
                <strong>Quality Team - Northwind</strong>
            </p>
        </div>
    </body>
    </html>
    """


#https://your-app.azurewebsites.net/assets/northwind-CfOjGbwW.png
