import base64
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.email_delivery import EmailDelivery

logger = logging.getLogger(__name__)

GRAPH_SENDER_MAILBOX = os.getenv("GRAPH_SENDER_MAILBOX")
GRAPH_FROM_EMAIL = os.getenv("GRAPH_FROM_EMAIL") or GRAPH_SENDER_MAILBOX
GRAPH_FROM_NAME = os.getenv("GRAPH_FROM_NAME", "Audit Manager")
GRAPH_TIMEOUT_SECONDS = int(os.getenv("GRAPH_TIMEOUT_SECONDS", "30"))
DEFAULT_MAX_RETRIES = int(os.getenv("EMAIL_MAX_RETRIES", "3"))
DEFAULT_RETRY_DELAY_SECONDS = int(os.getenv("EMAIL_RETRY_DELAY_SECONDS", "2"))


def _normalize_recipients(recipients: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for recipient in recipients:
        value = str(recipient).strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(value)
    return normalized


def _create_delivery(
    db: Optional[Session],
    *,
    subject: str,
    recipients: list[str],
    cc: Optional[list[str]],
    context: Optional[str],
) -> Optional[EmailDelivery]:
    if db is None:
        return None
    try:
        delivery = EmailDelivery(
            subject=subject,
            recipients=",".join(recipients),
            cc=",".join(cc) if cc else None,
            status="pending",
            attempts=0,
            context=context,
            created_at=datetime.now(timezone.utc),
        )
        db.add(delivery)
        db.commit()
        db.refresh(delivery)
        return delivery
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception(
            "email_delivery_create_failed subject=%s recipients=%s error=%s",
            subject,
            recipients,
            exc,
        )
        return None


def _update_delivery(
    db: Optional[Session],
    delivery: Optional[EmailDelivery],
    *,
    status: str,
    attempts: int,
    error: Optional[str] = None,
    sent: bool = False,
) -> None:
    if db is None or delivery is None:
        return
    try:
        delivery.status = status
        delivery.attempts = attempts
        delivery.error = error
        delivery.last_attempt_at = datetime.now(timezone.utc)
        if sent:
            delivery.sent_at = datetime.now(timezone.utc)
        db.add(delivery)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception(
            "email_delivery_update_failed id=%s status=%s error=%s",
            getattr(delivery, "id", None),
            status,
            exc,
        )


def _get_graph_access_token() -> str:
    identity_endpoint = os.getenv("IDENTITY_ENDPOINT")
    identity_header = os.getenv("IDENTITY_HEADER")

    if not identity_endpoint or not identity_header:
        raise RuntimeError(
            "Azure Managed Identity is not available. "
            "IDENTITY_ENDPOINT/IDENTITY_HEADER are missing."
        )

    params = urllib.parse.urlencode(
        {
            "resource": "https://graph.microsoft.com",
            "api-version": "2019-08-01",
        }
    )
    request = urllib.request.Request(
        f"{identity_endpoint}?{params}",
        headers={"X-IDENTITY-HEADER": identity_header},
    )

    with urllib.request.urlopen(request, timeout=GRAPH_TIMEOUT_SECONDS) as response:
        payload = json.loads(response.read().decode("utf-8"))

    access_token = payload.get("access_token")
    if not access_token:
        raise RuntimeError("Managed Identity did not return a Microsoft Graph access token.")
    return access_token


def _graph_recipient(address: str, name: Optional[str] = None) -> dict:
    email_address: dict[str, str] = {"address": address}
    if name:
        email_address["name"] = name
    return {"emailAddress": email_address}


def _build_graph_message(
    *,
    subject: str,
    recipients: list[str],
    cc: list[str],
    body_html: str,
    attachment_path: Optional[str],
    attachment_filename: Optional[str],
    sender_email: Optional[str],
    sender_name: Optional[str],
    reply_to: Optional[str],
) -> dict:
    if not GRAPH_SENDER_MAILBOX:
        raise RuntimeError("GRAPH_SENDER_MAILBOX is not configured.")

    from_email = GRAPH_FROM_EMAIL or GRAPH_SENDER_MAILBOX
    from_name = GRAPH_FROM_NAME or sender_name or ""

    message: dict = {
        "subject": subject,
        "body": {
            "contentType": "HTML",
            "content": body_html,
        },
        "toRecipients": [_graph_recipient(address) for address in recipients],
        "from": _graph_recipient(from_email, from_name),
    }

    if cc:
        message["ccRecipients"] = [_graph_recipient(address) for address in cc]

    effective_reply_to = reply_to or sender_email
    if effective_reply_to:
        message["replyTo"] = [_graph_recipient(effective_reply_to)]

    if attachment_path:
        if not os.path.exists(attachment_path):
            raise FileNotFoundError(f"Email attachment not found: {attachment_path}")

        with open(attachment_path, "rb") as file_handle:
            attachment_bytes = file_handle.read()

        message["attachments"] = [
            {
                "@odata.type": "#microsoft.graph.fileAttachment",
                "name": attachment_filename or os.path.basename(attachment_path),
                "contentType": "application/pdf",
                "contentBytes": base64.b64encode(attachment_bytes).decode("ascii"),
            }
        ]

    return message


def _send_graph_message(message: dict) -> None:
    if not GRAPH_SENDER_MAILBOX:
        raise RuntimeError("GRAPH_SENDER_MAILBOX is not configured.")

    access_token = _get_graph_access_token()
    encoded_mailbox = urllib.parse.quote(GRAPH_SENDER_MAILBOX, safe="")
    graph_url = f"https://graph.microsoft.com/v1.0/users/{encoded_mailbox}/sendMail"

    payload = json.dumps(
        {
            "message": message,
            "saveToSentItems": True,
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        graph_url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=GRAPH_TIMEOUT_SECONDS) as response:
            if response.status != 202:
                raise RuntimeError(
                    f"Unexpected Microsoft Graph sendMail status: {response.status}"
                )
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8")
        except Exception:
            detail = str(exc)
        raise RuntimeError(
            f"Microsoft Graph sendMail failed with HTTP {exc.code}: {detail}"
        ) from exc


def send_email_sync_tracked(
    *,
    subject: str,
    recipients: list[str],
    body_html: str,
    cc: Optional[list[str]] = None,
    db: Optional[Session] = None,
    context: Optional[str] = None,
    max_retries: Optional[int] = None,
    retry_delay_seconds: Optional[int] = None,
    attachment_path: Optional[str] = None,
    attachment_filename: Optional[str] = None,
    sender_email: Optional[str] = None,
    sender_name: Optional[str] = None,
    reply_to: Optional[str] = None,
) -> bool:
    recipients = _normalize_recipients(recipients)
    cc = _normalize_recipients(cc or [])

    if not recipients:
        raise ValueError("At least one recipient is required.")

    recipient_keys = {recipient.lower() for recipient in recipients}
    cc = [recipient for recipient in cc if recipient.lower() not in recipient_keys]

    retries = max_retries if max_retries is not None else DEFAULT_MAX_RETRIES
    delay = (
        retry_delay_seconds
        if retry_delay_seconds is not None
        else DEFAULT_RETRY_DELAY_SECONDS
    )

    delivery = _create_delivery(
        db,
        subject=subject,
        recipients=recipients,
        cc=cc,
        context=context,
    )

    message = _build_graph_message(
        subject=subject,
        recipients=recipients,
        cc=cc,
        body_html=body_html,
        attachment_path=attachment_path,
        attachment_filename=attachment_filename,
        sender_email=sender_email,
        sender_name=sender_name,
        reply_to=reply_to,
    )

    last_error: Optional[str] = None
    for attempt in range(1, retries + 1):
        try:
            _send_graph_message(message)
            _update_delivery(db, delivery, status="sent", attempts=attempt, sent=True)
            logger.info(
                "email_sent_via_graph subject=%s recipients=%s",
                subject,
                recipients,
            )
            return True
        except Exception as exc:
            last_error = str(exc)
            status = "retrying" if attempt < retries else "failed"
            _update_delivery(
                db,
                delivery,
                status=status,
                attempts=attempt,
                error=last_error,
                sent=False,
            )
            logger.exception(
                "email_graph_send_failed subject=%s recipients=%s attempt=%s/%s error=%s",
                subject,
                recipients,
                attempt,
                retries,
                last_error,
            )
            if attempt < retries:
                time.sleep(delay)

    return False


async def send_email_async_tracked(
    *,
    subject: str,
    recipients: list[str],
    body_html: str,
    cc: Optional[list[str]] = None,
    db: Optional[Session] = None,
    context: Optional[str] = None,
    max_retries: Optional[int] = None,
    sender_email: Optional[str] = None,
    sender_name: Optional[str] = None,
    reply_to: Optional[str] = None,
) -> dict:
    success = send_email_sync_tracked(
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
    if not success:
        raise Exception("Error sending email")
    return {"status": "Email sent successfully!"}
