from sqlalchemy import Enum

audit_status_enum = Enum(
    "planned",
    "rescheduled",
    "postponed",
    "waiting_for_corrective_actions",
    "completed",
    "cancelled",
    name="audit_status"
)

ca_status_enum = Enum(
    "pending",
    "submitted",
    "accepted",
    "rejected",
    "closed",
    name="ca_status"
)

plant_type_enum = Enum(
    "atlas","frankfort","rayones","carthage","medina","daegu",
    "monterrey","anhui","galeana","poitiers","tianjin",
    "kunshan","chennai","loire",
    name="plant_type"
)

audit_action_enum = Enum(
    "rescheduled",
    "postponed",
    "cancelled",
    "closed",
    "auditees_updated",
    name="audit_action"
)

ca_decision_enum = Enum(
    "accepted",
    "rejected",
    name="ca_decision"
)
