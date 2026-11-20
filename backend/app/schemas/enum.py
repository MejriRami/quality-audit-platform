 
from sqlalchemy.orm import  declarative_base
import enum
 

Base = declarative_base()

# =====================================================
# ENUMS
# =====================================================

class AuditStatusEnum(str, enum.Enum):
    planned = "planned"
    rescheduled = "rescheduled"
    waiting_for_corrective_actions = "waiting_for_corrective_actions"
    completed = "completed"
    cancelled = "cancelled"


class CAStatusEnum(str, enum.Enum):
    pending = "pending"
    submitted = "submitted"
    accepted = "accepted"
    rejected = "rejected"
    closed = "closed"


class PlantEnum(str, enum.Enum):
    atlas = "atlas"
    frankfort = "frankfort"
    rayones = "rayones"
    same = "carthage"
    medina = "medina"
    daegu = "daegu"
    monterrey = "monterrey"
    anhui = "anhui"
    galeana = "galeana"
    poitiers = "poitiers"
    tianjin = "tianjin"
    kunshan = "kunshan"
    chennai = "chennai"
    loire = "loire"


class AuditActionEnum(str, enum.Enum):
    rescheduled = "rescheduled"
    postponed = "postponed"
    cancelled = "cancelled"
    closed = "closed"
    auditees_updated = "auditees_updated"


class CADecisionEnum(str, enum.Enum):
    accepted = "accepted"
    rejected = "rejected"

