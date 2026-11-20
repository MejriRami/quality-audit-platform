import { Navigate, Outlet, useLocation } from "react-router";
import { useSelector } from "react-redux";
import { RootState } from "../../redux/store";
import { hasSystemAdminRole } from "../../utils/roleAccess";

export default function RequireAdmin() {
  const location = useLocation();
  const roles = useSelector((state: RootState) => state.auth.role || []);
  const isAdmin = hasSystemAdminRole(roles);

  if (!isAdmin) {
    return <Navigate to="/home" state={{ from: location }} replace />;
  }

  return <Outlet />;
}
