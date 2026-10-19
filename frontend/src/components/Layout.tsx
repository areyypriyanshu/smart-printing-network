import { Suspense, useState } from "react";
import { Link, Outlet, useNavigate } from "react-router";

import { useSession } from "../features/auth";
import { Button } from "./ui";

export function Layout() {
  const { status, user, logout } = useSession();
  const navigate = useNavigate();
  const [pending, setPending] = useState(false);

  const onLogout = async () => {
    setPending(true);
    try {
      await logout();
      void navigate("/login", { replace: true });
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-hairline-soft bg-canvas">
        <div className="mx-auto flex w-full max-w-4xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <Link
            to="/"
            className="text-base font-semibold tracking-tight text-ink"
          >
            Smart Printing Network
          </Link>
          <nav
            aria-label="Main"
            className="flex flex-wrap items-center gap-4 text-sm"
          >
            {status === "authenticated" && user !== null ? (
              <>
                {user.role === "vendor" && (
                  <>
                    <Link
                      className="text-ink hover:text-primary"
                      to="/vendor/rates"
                    >
                      Rates
                    </Link>
                    <Link
                      className="text-ink hover:text-primary"
                      to="/vendor/settings"
                    >
                      Shop settings
                    </Link>
                  </>
                )}
                <span className="text-steel">{user.email}</span>
                <Button
                  variant="secondary"
                  pending={pending}
                  pendingLabel="Signing out…"
                  onClick={onLogout}
                >
                  Sign out
                </Button>
              </>
            ) : status === "anonymous" ? (
              <>
                <Link className="text-ink hover:text-primary" to="/login">
                  Sign in
                </Link>
                <Link className="text-ink hover:text-primary" to="/register">
                  Create account
                </Link>
              </>
            ) : null}
          </nav>
        </div>
      </header>
      <main className="flex-1">
        <Suspense
          fallback={
            <p role="status" className="p-6 text-steel">
              Loading…
            </p>
          }
        >
          <Outlet />
        </Suspense>
      </main>
      <div className="sunset-stripe h-2" aria-hidden="true" />
      <footer className="border-t border-beige-deep bg-cream">
        <p className="mx-auto w-full max-w-4xl px-4 py-3 text-sm text-steel">
          Pick up your prints from a verified shop near you.
        </p>
      </footer>
    </div>
  );
}
