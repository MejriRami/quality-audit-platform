from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
import asyncio
from dotenv import load_dotenv

from app.config.database import get_db, SessionLocal
from app.schemas.notificationSchema.notification import NotificationListResponse, UnreadCountResponse
from app.services import notification_service
from app.services.auth_service import get_current_user, verify_token
from app.config.connection_manager import manager
import logging

load_dotenv()
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket
):
    """
    WebSocket endpoint for real-time notifications
    Authentication flow:
    1) Client connects to /notifications/ws
    2) Client sends first message:
       {"type": "auth", "token": "<JWT>"}
    """
    user = None
    db = None
    
    try:
        await websocket.accept()

        # Require auth as first message to avoid token in URL logs.
        try:
            auth_message = await asyncio.wait_for(websocket.receive_json(), timeout=10)
            token = auth_message.get("token") if isinstance(auth_message, dict) else None
            message_type = auth_message.get("type") if isinstance(auth_message, dict) else None
        except asyncio.TimeoutError:
            logger.warning("WebSocket auth timeout")
            await websocket.close(code=1008, reason="Authentication required")
            return
        except Exception:
            logger.warning("WebSocket auth payload invalid")
            await websocket.close(code=1008, reason="Invalid authentication payload")
            return

        if message_type != "auth" or not token:
            await websocket.close(code=1008, reason="Authentication required")
            return

        db = SessionLocal()
        user = verify_token(token, db)
        
        if not user:
            await websocket.close(code=1008, reason="Invalid or expired token")
            return
        
        # Connect user
        await manager.connect(user.id, websocket)
        
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connection",
            "message": "Connected to notification service",
            "user_id": user.id
        })
        
        # Keep connection alive and handle incoming messages
        try:
            while True:
                # Receive heartbeat or other messages from client
                data = await websocket.receive_text()
                
                # Optional: Handle ping/pong
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
                    
        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected for user {user.id}")
        except Exception as e:
            logger.error(f"WebSocket error for user {user.id}: {e}")
        finally:
            if user:
                await manager.disconnect(user.id, websocket)
            if db is not None:
                db.close()
            
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
        if db is not None:
            db.close()
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except Exception:
            pass


@router.get("/", response_model=NotificationListResponse)
async def get_notifications(
    unread_only: bool = False,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get all notifications for current user"""
    result = notification_service.get_user_notifications(
        db=db,
        user_id=current_user.id,
        unread_only=unread_only,
        limit=limit
    )
    return result

@router.get("/unread-count", response_model=UnreadCountResponse)
async def get_unread_count(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get count of unread notifications"""
    count = notification_service.get_unread_count_from_db(db, current_user.id)
    return {"unread_count": count}

@router.put("/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Mark a notification as read"""
    success = notification_service.mark_notification_as_read_in_db(
        db, notification_id, current_user.id
    )
    
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    return {"message": "Notification marked as read", "notification_id": notification_id}

@router.put("/read-all")
async def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Mark all notifications as read"""
    count = notification_service.mark_all_as_read_in_db(db, current_user.id)
    return {"message": f"{count} notifications marked as read"}


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Delete a notification"""
    return await notification_service.delete_notification(
        notification_id=notification_id,
        db=db,
        user_id=current_user.id
    )
