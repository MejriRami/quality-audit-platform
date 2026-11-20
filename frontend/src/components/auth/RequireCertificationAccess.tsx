import { Navigate, Outlet, useLocation } from "react-router";
import { canViewExternalCertifications } from "../../utils/roleAccess";

export default function RequireCertificationAccess() {
  const location = useLocation();

  if (!canViewExternalCertifications()) {
    return <Navigate to="/home" state={{ from: location }} replace />;
  }

  return <Outlet />;
}
