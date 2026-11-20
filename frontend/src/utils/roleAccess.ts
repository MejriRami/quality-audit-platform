export const SYSTEM_ADMIN_ROLES = ["admin"] as const;
export const QUALITY_MANAGER_ROLES = [
  "quality_manager",
  "quality manager",
  "quality-manager",
] as const;
export const AUDITOR_ROLE = "auditor";
export const TOP_MANAGEMENT_ROLES = [
  "top_management",
  "top management",
  "top-management",
] as const;
export const CERTIFICATION_EDITOR_ROLE = "certification_editor";
export const CERTIFICATION_VIEWER_ROLE = "certification_viewer";

export const normalizeRoles = (roles: unknown[] = []) =>
  roles.map((role) => String(role).trim().toLowerCase());

export const hasSystemAdminRole = (roles: unknown[] = []) =>
  normalizeRoles(roles).some((role) =>
    SYSTEM_ADMIN_ROLES.includes(role as (typeof SYSTEM_ADMIN_ROLES)[number]),
  );

export const hasQualityManagerRole = (roles: unknown[] = []) =>
  normalizeRoles(roles).some((role) =>
    QUALITY_MANAGER_ROLES.includes(
      role as (typeof QUALITY_MANAGER_ROLES)[number],
    ),
  );

export const hasAuditorRole = (roles: unknown[] = []) =>
  normalizeRoles(roles).includes(AUDITOR_ROLE);

export const hasTopManagementRole = (roles: unknown[] = []) =>
  normalizeRoles(roles).some((role) =>
    TOP_MANAGEMENT_ROLES.includes(role as (typeof TOP_MANAGEMENT_ROLES)[number]),
  );

export const canViewSilentBox = (roles: unknown[] = []) =>
  hasSystemAdminRole(roles) ||
  hasQualityManagerRole(roles) ||
  hasAuditorRole(roles) ||
  hasTopManagementRole(roles);

export const canManageFrameworks = (roles: unknown[] = []) =>
  hasSystemAdminRole(roles) ||
  hasQualityManagerRole(roles) ||
  hasAuditorRole(roles);

export const canManageQuestionnaires = (roles: unknown[] = []) =>
  canManageFrameworks(roles);

export const canManagePlantHolidays = (roles: unknown[] = []) =>
  hasQualityManagerRole(roles) || hasAuditorRole(roles);

export const canPlanAudits = (roles: unknown[] = []) =>
  hasSystemAdminRole(roles) || hasQualityManagerRole(roles);

// Every signed-in user can consult the certifications.
export const canViewExternalCertifications = () => true;

// Quality managers, group internal auditors and certification editors
// (quality engineers / quality system managers get certification_editor).
export const canEditExternalCertifications = (roles: unknown[] = []) =>
  hasSystemAdminRole(roles) ||
  hasQualityManagerRole(roles) ||
  hasAuditorRole(roles) ||
  normalizeRoles(roles).includes(CERTIFICATION_EDITOR_ROLE);

// Users migrated from the standalone certification app hold only
// certification roles: they get that page and nothing of the audit app.
export const isCertificationOnlyUser = (roles: unknown[] = []) => {
  const normalized = normalizeRoles(roles);
  return (
    normalized.length > 0 &&
    normalized.every(
      (role) =>
        role === CERTIFICATION_EDITOR_ROLE || role === CERTIFICATION_VIEWER_ROLE,
    )
  );
};
