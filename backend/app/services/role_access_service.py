from app.models.user import User

SYSTEM_ADMIN_ROLE_NAMES = {"admin"}
QUALITY_MANAGER_ROLE_NAMES = {
    "quality_manager",
    "quality manager",
    "quality-manager",
}
ADMIN_ROLE_NAMES = SYSTEM_ADMIN_ROLE_NAMES | QUALITY_MANAGER_ROLE_NAMES
AUDITOR_ROLE_NAME = "auditor"
TOP_MANAGEMENT_ROLE_NAMES = {
    "top_management",
    "top management",
    "top-management",
}
CERTIFICATION_EDITOR_ROLE_NAME = "certification_editor"
CERTIFICATION_VIEWER_ROLE_NAME = "certification_viewer"


def role_names(user: User) -> set[str]:
    return {
        (getattr(getattr(ur, "role", None), "name", "") or "").strip().lower()
        for ur in (user.roles or [])
        if getattr(getattr(ur, "role", None), "name", None)
    }


def is_admin_or_quality_manager(user: User) -> bool:
    return bool(role_names(user).intersection(ADMIN_ROLE_NAMES))


def has_admin_role(user: User) -> bool:
    return bool(role_names(user).intersection(SYSTEM_ADMIN_ROLE_NAMES))


def has_quality_manager_role(user: User) -> bool:
    return bool(role_names(user).intersection(QUALITY_MANAGER_ROLE_NAMES))


def is_restricted_auditor(user: User) -> bool:
    roles = role_names(user)
    return AUDITOR_ROLE_NAME in roles and not roles.intersection(ADMIN_ROLE_NAMES)


def has_auditor_role(user: User) -> bool:
    return AUDITOR_ROLE_NAME in role_names(user)


def has_top_management_role(user: User) -> bool:
    return bool(role_names(user).intersection(TOP_MANAGEMENT_ROLE_NAMES))


def can_view_silent_box(user: User) -> bool:
    return bool(
        has_admin_role(user)
        or has_quality_manager_role(user)
        or has_auditor_role(user)
        or has_top_management_role(user)
    )


def can_manage_frameworks(user: User) -> bool:
    roles = role_names(user)
    return bool(
        roles.intersection(SYSTEM_ADMIN_ROLE_NAMES | QUALITY_MANAGER_ROLE_NAMES)
        or AUDITOR_ROLE_NAME in roles
    )


def can_manage_questionnaires(user: User) -> bool:
    roles = role_names(user)
    return bool(
        roles.intersection(SYSTEM_ADMIN_ROLE_NAMES | QUALITY_MANAGER_ROLE_NAMES)
        or AUDITOR_ROLE_NAME in roles
    )


def can_manage_plant_holidays(user: User) -> bool:
    roles = role_names(user)
    return bool(
        roles.intersection(QUALITY_MANAGER_ROLE_NAMES) or AUDITOR_ROLE_NAME in roles
    )


def can_view_external_certifications(user: User) -> bool:
    # Every signed-in user can consult the certifications.
    return user is not None


def can_edit_external_certifications(user: User) -> bool:
    # Quality managers, group internal auditors and certification editors
    # (quality engineers / quality system managers get certification_editor).
    roles = role_names(user)
    return bool(
        roles.intersection(SYSTEM_ADMIN_ROLE_NAMES | QUALITY_MANAGER_ROLE_NAMES)
        or AUDITOR_ROLE_NAME in roles
        or CERTIFICATION_EDITOR_ROLE_NAME in roles
    )
