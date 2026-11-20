import random
import string
from app.models.audit import Audit
from app.schemas.auditSchema.auditSchema import AuditPickerItem

def generate_audit_number():
    return "A-" + "".join(random.choices(string.digits, k=5))


def parse_name_from_email(email: str):
    """
    Extract first and last name from emails like first.last@domain.com.
    Returns (first, last). Robust against underscores/dashes.
    """
    try:
        local = email.split("@")[0]
    except:
        local = email

    normalized = (
        local.replace("_", ".")
        .replace("-", ".")
    )
    parts = [p for p in normalized.split(".") if p]

    if not parts:
        return "", ""

    first = parts[0].capitalize()
    last = parts[1].capitalize() if len(parts) > 1 else ""

    return first, last

def map_audit_to_picker(audit: Audit) -> AuditPickerItem:
    return AuditPickerItem(
        id=audit.id,
        audit_number=audit.audit_number,
        planned_date=audit.planned_start_date.date().isoformat(),
        planned_start_time=audit.planned_start_date.strftime("%H:%M"),
        planned_end_time=audit.planned_end_date.strftime("%H:%M"),
        status=audit.status,
        auditees=audit.auditees,
        questionnaire_name=audit.questionnaire.name if audit.questionnaire else None,
        plant=audit.plant.upper() if audit.plant else None,
        framework_code=getattr(getattr(audit.questionnaire, "framework", None), "code", None),
        framework_label=getattr(getattr(audit.questionnaire, "framework", None), "label", None),
        audit_type_value=getattr(getattr(audit.questionnaire, "audit_type", None), "value", None),
        score_calculation=getattr(audit.questionnaire, "score_calculation", None),
    )
