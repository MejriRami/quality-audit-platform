"""
notification_service.py
-----------------------
All database interactions for the Notification model.

Key fixes vs. original:
- create_and_send_notification now writes to `meta_data` (the real column
  name) instead of the nonexistent `metadata` kwarg, which was silently
  dropped by SQLAlchemy.
- notification_to_dict uses a safe JSON parse that logs bad data instead
  of crashing.
- delete_notification is now a plain sync function (no async needed for
  pure DB work) and raises HTTPException on 404.
- Type hints are complete.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.config.connection_manager import manager
from app.models.notification import Notification

logger = logging.getLogger(__name__)


# ── Serialisation ──────────────────────────────────────────────────────────────

def _safe_json_loads(raw: Optional[str]) -> Optional[Any]:
    """Parse JSON without raising; logs a warning on malformed data."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("notification meta_data is not valid JSON: %.120s", raw)
        return None


def notification_to_dict(notification: Notification) -> Dict[str, Any]:
    return {
        "id": notification.id,
        "type": notification.type,
        "title": notification.title,
        "message": notification.message,
        "link": notification.link,
        "read": notification.read,
        "created_at": notification.created_at.isoformat(),
        "metadata": _safe_json_loads(notification.meta_data),
    }


# ── Queries ────────────────────────────────────────────────────────────────────

def get_notifications_from_db(
    db: Session,
    user_id: int,
    unread_only: bool = False,
    limit: int = 50,
) -> List[Notification]:
    query = db.query(Notification).filter(Notification.user_id == user_id)
    if unread_only:
        query = query.filter(Notification.read == False)  # noqa: E712
    return query.order_by(Notification.created_at.desc()).limit(limit).all()


def get_unread_count_from_db(db: Session, user_id: int) -> int:
    return (
        db.query(Notification)
        .filter(
            and_(
                Notification.user_id == user_id,
                Notification.read == False,  # noqa: E712
            )
        )
        .count()
    )


# ── Mutations ──────────────────────────────────────────────────────────────────

def mark_notification_as_read_in_db(
    db: Session,
    notification_id: int,
    user_id: int,
) -> bool:
    notification = (
        db.query(Notification)
        .filter(
            and_(
                Notification.id == notification_id,
                Notification.user_id == user_id,
            )
        )
        .first()
    )

    if notification and not notification.read:
        notification.read = True
        db.commit()
        logger.info("notification_read id=%s user_id=%s", notification_id, user_id)
        return True
    return False


def mark_all_as_read_in_db(db: Session, user_id: int) -> int:
    count = (
        db.query(Notification)
        .filter(
            and_(
                Notification.user_id == user_id,
                Notification.read == False,  # noqa: E712
            )
        )
        .update({"read": True}, synchronize_session=False)
    )
    db.commit()
    logger.info("notifications_mark_all_read user_id=%s count=%s", user_id, count)
    return count


def delete_old_notifications_from_db(db: Session, days: int = 30) -> int:
    cutoff_date = datetime.now() - timedelta(days=days)
    count = (
        db.query(Notification)
        .filter(
            and_(
                Notification.read == True,  # noqa: E712
                Notification.created_at < cutoff_date,
            )
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    logger.info("notifications_purged days=%s count=%s", days, count)
    return count


def delete_notification(db: Session, notification_id: int) -> Dict[str, Any]:
    """Delete a notification by ID. Raises HTTPException 404 if not found."""
    notification = (
        db.query(Notification).filter(Notification.id == notification_id).first()
    )
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    db.delete(notification)
    db.commit()
    return {"id": notification_id, "message": "Notification deleted successfully"}


# ── Create + push ──────────────────────────────────────────────────────────────

async def create_and_send_notification(
    db: Session,
    user_id: int,
    notification_type: str,
    title: str,
    message: str,
    link: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Notification:
    """
    Persist a notification and push it to the user's open WebSocket(s).

    The `metadata` dict is serialised to JSON and stored in the `meta_data`
    column.  The WebSocket payload uses the key `metadata` to match the
    frontend NotificationItem type.
    """
    meta_json = json.dumps(metadata) if metadata else None

    notification = Notification(
        user_id=user_id,
        type=notification_type,
        title=title,
        message=message,
        link=link,
        meta_data=meta_json,   # ← correct column name
        read=False,
        created_at=datetime.now(),
    )

    db.add(notification)
    db.commit()
    db.refresh(notification)

    ws_payload = {
        "id": notification.id,
        "type": notification_type,
        "title": title,
        "message": message,
        "link": link,
        "metadata": metadata,  # already a dict — no need to re-parse
        "read": False,
        "created_at": notification.created_at.isoformat(),
    }

    await manager.send_personal_notification(user_id, ws_payload)
    return notification


# ── Composite read ─────────────────────────────────────────────────────────────

def get_user_notifications(
    db: Session,
    user_id: int,
    unread_only: bool = False,
    limit: int = 50,
) -> Dict[str, Any]:
    notifications = get_notifications_from_db(db, user_id, unread_only, limit)
    unread_count = get_unread_count_from_db(db, user_id)
    return {
        "notifications": [notification_to_dict(n) for n in notifications],
        "unread_count": unread_count,
    }