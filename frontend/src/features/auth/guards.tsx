import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import type { Role } from "../../api/client";
import { ForbiddenPage } from "../../components/StatusPages";
import { useSession } from "./session";

export function SessionLoading() {
  return (
    <p role="status" className="p-6 text-slate-600">
      Loading…
    </p>
  );
}

export function RequireAuth({ children }: { children: ReactNode }) {
  const { status } = useSession();
  const location = useLocation();

  if (status === "loading") return <SessionLoading />;
  if (status === "anonymous") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}

export function RequireRole({
  role,
  children,
}: {
  role: Role;
  children: ReactNode;
}) {
  const { user } = useSession();

  if (user === null) return <SessionLoading />;
  if (user.role !== role) return <ForbiddenPage />;
  return <>{children}</>;
}
