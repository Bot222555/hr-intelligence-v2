/**
 * RoleGuard — Protects routes by checking user role.
 * Redirects to dashboard if the user's role is not in the allowed list.
 */

import { Navigate } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import type { UserRole } from "@/lib/types";

interface RoleGuardProps {
  allowedRoles: UserRole[];
  children: React.ReactNode;
}

export function RoleGuard({ allowedRoles, children }: RoleGuardProps) {
  const { user } = useAuth();

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (!allowedRoles.includes(user.role)) {
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
}
