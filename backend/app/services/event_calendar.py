# -------------------------
# Imports
# -------------------------
import os
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

# MS Graph SDK imports
from msgraph import GraphServiceClient
from msgraph.generated.models.event import Event
from msgraph.generated.models.item_body import ItemBody
from msgraph.generated.models.date_time_time_zone import DateTimeTimeZone
from msgraph.generated.models.attendee import Attendee
from msgraph.generated.models.email_address import EmailAddress
from msgraph.generated.models.body_type import BodyType

# Azure Identity for auth
from azure.identity.aio import ClientSecretCredential

# HTTP client for raw requests
import httpx


# -------------------------
# Environment / Config
# -------------------------
TENANT_ID = os.getenv("AZURE_TENANT_ID")
CLIENT_ID = os.getenv("AZURE_CLIENT_ID")
CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET")

SP_ROOT_FOLDER = os.environ.get("SP_ROOT_FOLDER", "audit-reports-2026")
OUTLOOK_LOCAL_TIMEZONE = os.environ.get("OUTLOOK_LOCAL_TIMEZONE", "Africa/Lagos")
# -------------------------
# Authentication / Graph client
# -------------------------
# Using application permission (client credentials)
credential = ClientSecretCredential(
    tenant_id=TENANT_ID,
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
)

scopes = ["https://graph.microsoft.com/.default"]
# scopes = ["Calendars.ReadWrite"]  # this for delegated permissions

# Graph client instance
client = GraphServiceClient(credentials=credential, scopes=scopes)


# -------------------------
# Utility: Get access token
# -------------------------
async def get_access_token() -> str:
    """
    Get a Microsoft Graph API access token using application credentials.
    Make sure to close the credential to avoid unclosed session warnings.
    """
    credential = ClientSecretCredential(
        tenant_id=TENANT_ID, client_id=CLIENT_ID, client_secret=CLIENT_SECRET
    )
    token = await credential.get_token("https://graph.microsoft.com/.default")
    await credential.close()
    return token.token


def _to_utc_datetime(dt: datetime) -> datetime:
    """
    Normalize datetime values to aware UTC.
    If a datetime is naive, interpret it in OUTLOOK_LOCAL_TIMEZONE first.
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(OUTLOOK_LOCAL_TIMEZONE))
    return dt.astimezone(timezone.utc)


# -------------------------
# Check User Availability
# -------------------------
async def is_user_available(email: str, start: datetime, end: datetime) -> bool:
    """
    Check if a user is free between start and end, using getSchedule.
    Correctly interprets availability status and ignores free events.
    """
    token = await get_access_token()

    url = f"https://graph.microsoft.com/v1.0/users/{email}/calendar/getSchedule"
    body = {
        "schedules": [email],
        "startTime": {
            "dateTime": _to_utc_datetime(start).isoformat(),
            "timeZone": "UTC",
        },
        "endTime": {
            "dateTime": _to_utc_datetime(end).isoformat(),
            "timeZone": "UTC",
        },
        "availabilityViewInterval": 30,
    }

    async with httpx.AsyncClient() as http_client:
        resp = await http_client.post(
            url,
            json=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )

    resp.raise_for_status()
    data = resp.json()
    schedule = data.get("value", [])
    print("data is : ", data)
    if not schedule:
        return True  # No schedule data → assume user is free

    schedule_info = schedule[0]

    # ----------------------------------------------------------
    # 1 QUICK CHECK: availabilityView
    # ----------------------------------------------------------
    availability_view = schedule_info.get("availabilityView", "")
    if any(ch in ("1", "2", "3", "4") for ch in availability_view):
        return False

    # ----------------------------------------------------------
    # 2 DEEP CHECK: scheduleItems
    # ----------------------------------------------------------
    busy_items = schedule_info.get("scheduleItems", [])
    blocking_statuses = {"busy", "oof", "tentative", "workingElsewhere"}

    for item in busy_items:
        status = item.get("status", "free").lower()

        # ignore events that do NOT block time
        if status not in blocking_statuses:
            continue

        # Parse event times
        s = datetime.fromisoformat(item["start"]["dateTime"])
        e = datetime.fromisoformat(item["end"]["dateTime"])

        # Overlapping?
        if s < end and e > start:
            return False

    return True


# -------------------------
# Create Outlook Event
# -------------------------
async def create_event(
    subject: str,
    start: datetime,
    end: datetime,
    attendees_emails: list[str],
    body_text: str,
    auditor_email: str,
):
    """
    Create a calendar event in the auditor's mailbox with attendees.
    """
    attendees = [
        Attendee(email_address=EmailAddress(address=email), type="required")
        for email in attendees_emails
    ]

    event = Event(
        subject=subject,
        body=ItemBody(content_type=BodyType("html"), content=body_text),
        start=DateTimeTimeZone(
            date_time=_to_utc_datetime(start).isoformat(), time_zone="UTC"
        ),
        end=DateTimeTimeZone(
            date_time=_to_utc_datetime(end).isoformat(), time_zone="UTC"
        ),
        attendees=attendees,
        response_requested=True,
        is_online_meeting=False,
    )

    event.reminder_minutes_before_start = 30
    event.is_reminder_on = True

    # we must change either we send email using auditor EMAIL/or administrationSTS or delegated permission
    return await client.users.by_user_id(auditor_email).events.post(body=event)


async def modify_outlook_event(
    auditor_email: str,
    event_id: str,
    new_start: datetime | None = None,
    new_end: datetime | None = None,
    attendees_emails: list[str] | None = None,
    subject: str | None = None,
    body_text: str | None = None,
) -> dict:
    """
    Modify an existing event (preferred).
    Returns the updated event JSON on success.
    Raises httpx.HTTPError on network/HTTP failure.
    """
    token = await get_access_token()
    url = f"https://graph.microsoft.com/v1.0/users/{auditor_email}/events/{event_id}"
    payload = {}
    if new_start is not None:
        payload["start"] = {
            "dateTime": _to_utc_datetime(new_start).isoformat(),
            "timeZone": "UTC",
        }
    if new_end is not None:
        payload["end"] = {
            "dateTime": _to_utc_datetime(new_end).isoformat(),
            "timeZone": "UTC",
        }
    if subject is not None:
        payload["subject"] = subject
    if body_text is not None:
        payload["body"] = {
            "contentType": "html",
            "content": body_text,
        }
    if attendees_emails is not None:
        payload["attendees"] = [
            {
                "emailAddress": {"address": email},
                "type": "required",
            }
            for email in attendees_emails
        ]

    if not payload:
        return {}

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.patch(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
    resp.raise_for_status()
    return resp.json()


async def cancel_outlook_event(
    auditor_email: str,
    event_id: str,
    comment: str | None = None,
) -> None:
    """
    Cancel an existing Outlook meeting as the organizer.
    This sends the cancellation to attendees and moves the event to Deleted Items.
    """
    token = await get_access_token()
    url = f"https://graph.microsoft.com/v1.0/users/{auditor_email}/events/{event_id}/cancel"
    payload = {
        "comment": comment or "Audit cancelled from Audit Management application."
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
    resp.raise_for_status()


GRAPH_API_URL = "https://graph.microsoft.com/v1.0"


async def create_graph_subscription(user_email: str):
    """Crée une subscription Graph pour suivre tous les events d'un organisateur"""
    url = f"{GRAPH_API_URL}/subscriptions"
    access_token = await get_access_token()

    expiration = (datetime.utcnow() + timedelta(days=2)).isoformat() + "Z"

    payload = {
        "changeType": "updated,deleted",
        "notificationUrl": "https://your-app.azurewebsites.net/audits/webhook/outlook",
        "resource": f"users/{user_email}/events",
        "expirationDateTime": expiration,
        "clientState": "audit-secret",
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers)

        print("GRAPH STATUS:", resp.status_code)
        print("GRAPH RESPONSE:", resp.text)

        resp.raise_for_status()
        data = resp.json()
        return data  # contient subscription id et expiration


async def get_graph_event(event_id: str, access_token: str, user_email: str) -> dict:
    """
    Fetch full event details from Microsoft Graph API
    """
    url = f"{GRAPH_API_URL}/users/{user_email}/events/{event_id}"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, headers=headers)

        if resp.status_code == 404:
            print(f"⚠️ Event {event_id} not found (may have been deleted)")
            return {"isCancelled": True}

        resp.raise_for_status()
        event_data = resp.json()

        return event_data
