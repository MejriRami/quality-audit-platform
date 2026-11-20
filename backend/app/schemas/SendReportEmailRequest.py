from pydantic import BaseModel, EmailStr
from typing import List, Optional

class SendReportEmailRequest(BaseModel):
    """Request model for sending report emails"""
    recipients: List[EmailStr]
    include_auditor: bool = False
    custom_message: Optional[str] = None