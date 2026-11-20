from tenacity import retry, stop_after_attempt, wait_fixed
import httpx
from datetime import datetime, timezone

from app.services.event_calendar import create_event, is_user_available

# Retry up to 3 times, wait 2 seconds between attempts
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
async def safe_is_user_available(email: str, start: datetime, end: datetime) -> bool:
    return await is_user_available(email, start, end)

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
async def safe_create_event(subject, start, end, attendees_emails, body_text, auditor_email):
    return await create_event(subject, start, end, attendees_emails, body_text, auditor_email)
