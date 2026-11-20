import { Navigate, Outlet, useLocation } from "react-router";
import { useSelector } from "react-redux";
import { RootState } from "../../redux/store";
import { isCertificationOnlyUser } from "../../utils/roleAccess";

// Keeps certification-only accounts on their page instead of the audit app.
export default function RequireAuditAppAccess() {
  const location = useLocation();
  const roles = useSelector((state: RootState) => state.auth.role || []);

  if (isCertificationOnlyUser(roles)) {
    return <Navigate to="/external-certifications" state={{ from: location }} replace />;
  }

  return <Outlet />;
}
