from pydantic import BaseModel
from typing import List


class ConsolidateThemeReportRequest(BaseModel):
    """Request model for the cross-audit, theme-consolidated report."""
    audit_ids: List[int]
