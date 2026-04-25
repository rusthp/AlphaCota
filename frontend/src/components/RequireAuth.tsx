import { Navigate, useLocation } from "react-router-dom";
import { isAuthenticated } from "@/lib/auth";
import { ReactNode } from "react";

export default function RequireAuth({ children }: { children: ReactNode }) {
  const location = useLocation();
  if (!isAuthenticated()) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }
  return <>{children}</>;
}
