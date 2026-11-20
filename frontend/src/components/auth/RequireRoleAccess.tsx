import { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
import { useSelector } from "react-redux";
import { RootState } from "../../redux/store";
import {
  canManageFrameworks,
  canManagePlantHolidays,
  canPlanAudits,
  hasAuditorRole,
} from "../../utils/roleAccess";

type RequireRoleAccessProps = {
  children: ReactNode;
  mode: "framework" | "holidays" | "consolidation" | "planning";
};

export default function RequireRoleAccess({
  children,
  mode,
}: RequireRoleAccessProps) {
  const location = useLocation();
  const roles = useSelector((state: RootState) => state.auth.role || []);

  const allowed =
    mode === "framework"
      ? canManageFrameworks(roles)
      : mode === "holidays"
        ? canManagePlantHolidays(roles)
        : mode === "planning"
          ? canPlanAudits(roles)
          : hasAuditorRole(roles);

  if (!allowed) {
    return <Navigate to="/home" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}
