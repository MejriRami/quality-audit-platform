from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any

class NotificationBase(BaseModel):
    type: str
    title: str
    message: str
    link: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class NotificationCreate(NotificationBase):
    user_id: int

class NotificationResponse(NotificationBase):
    id: int
    user_id: int | None = None
    read: bool
    created_at: datetime
    
    class Config:
        from_attributes = True
      
        populate_by_name = True

class NotificationListResponse(BaseModel):
    notifications: list[NotificationResponse]
    unread_count: int

class UnreadCountResponse(BaseModel):
    unread_count: int