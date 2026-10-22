import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

import type { Role } from "../../api/client";
import { ForbiddenPage } from "../../components/StatusPages";
import { useSession } from "./session";

export function SessionLoading() {
  return (
    <p role="status" className="p-6 text-steel">
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
  if (status === "needs-onboarding") {
    // They have signed in but have not said what they are here for,
    // so there is no account to act as yet.
    return <Navigate to="/onboarding" replace />;
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
  const { user, status } = useSession();

  if (status === "loading") return <SessionLoading />;
  if (status === "needs-onboarding") {
    return <Navigate to="/onboarding" replace />;
  }
  if (user === null) return <SessionLoading />;
  if (user.role !== role) return <ForbiddenPage />;
  return <>{children}</>;
}

/**
 * The landing page, for the person who has signed in and not chosen yet.
 *
 * A person who signs in lands on the front page, and a person who has
 * signed in and has no account can do nothing at all until they have
 * said what they are here for. So they are asked the one question
 * first, rather than being left on a page with a sign in button they
 * have already used.
 */
export function SendToOnboarding({ children }: { children: ReactNode }) {
  const { status } = useSession();

  if (status === "needs-onboarding") {
    return <Navigate to="/onboarding" replace />;
  }
  return <>{children}</>;
}

/**
 * The page for the person who has not chosen yet.
 *
 * It is here rather than behind a guard, because a person who has
 * signed in and has no account is not refused: they are sent to the one
 * question that has to be answered.
 */
export function RequireOnboarding({ children }: { children: ReactNode }) {
  const { status } = useSession();

  if (status === "loading") return <SessionLoading />;
  if (status === "anonymous") return <Navigate to="/login" replace />;
  if (status === "authenticated") return <Navigate to="/" replace />;
  return <>{children}</>;
}
