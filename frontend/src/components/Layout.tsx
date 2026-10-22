import { Suspense, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router";

import { useSession } from "../features/auth";
import { cn } from "../lib/cn";
import { Button, Icon } from "./ui";

const GITHUB_URL = "https://github.com/areyypriyanshu/smart-printing-network";

const desktopLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "rounded-md px-2 py-2 text-sm transition-colors duration-150 hover:text-primary",
    isActive ? "font-medium text-primary" : "text-ink",
  );

const mobileLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    "flex min-h-11 items-center rounded-md px-2 text-sm transition-colors duration-150",
    isActive ? "font-medium text-primary" : "text-ink hover:bg-surface",
  );

type NavItem = { to: string; label: string };

export function Layout() {
  const { status, user, logout } = useSession();
  const navigate = useNavigate();
  const [pending, setPending] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  const items: NavItem[] =
    user?.role === "vendor"
      ? [
          { to: "/vendor", label: "Queue" },
          { to: "/vendor/rates", label: "Rates" },
          { to: "/vendor/settings", label: "Shop settings" },
        ]
      : user?.role === "admin"
        ? [{ to: "/admin/shops", label: "Shops" }]
        : [
            { to: "/new", label: "New order" },
            { to: "/orders", label: "My orders" },
          ];

  const closeMenu = () => setMenuOpen(false);

  const onLogout = async () => {
    setPending(true);
    try {
      await logout();
      void navigate("/login", { replace: true });
    } finally {
      setPending(false);
    }
  };

  const signedIn = status === "authenticated" && user !== null;

  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:inline-flex focus:min-h-11 focus:items-center focus:rounded-lg focus:bg-canvas focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-ink focus:outline-2 focus:outline-primary"
      >
        Skip to content
      </a>
      <header className="border-b border-hairline bg-canvas">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-3 px-4 py-3">
          <Link
            to="/"
            onClick={closeMenu}
            className="flex min-h-11 items-center gap-2"
          >
            <img src="/favicon.svg" alt="" width={26} height={26} />
            <span className="font-display text-base font-bold tracking-tight text-ink">
              Smart Printing Network
            </span>
          </Link>
          <nav aria-label="Main" className="hidden items-center gap-2 md:flex">
            {signedIn ? (
              <>
                {items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={desktopLinkClass}
                  >
                    {item.label}
                  </NavLink>
                ))}
                <span className="px-1 text-sm text-steel">{user.email}</span>
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
                <NavLink to="/login" className={desktopLinkClass}>
                  Sign in
                </NavLink>
                <NavLink to="/register" className={desktopLinkClass}>
                  Create an account
                </NavLink>
              </>
            ) : null}
          </nav>
          <button
            type="button"
            className="inline-flex h-11 w-11 items-center justify-center rounded-lg text-ink transition-colors duration-150 hover:bg-surface focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary md:hidden"
            aria-expanded={menuOpen}
            aria-controls="mobile-nav"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            onClick={() => setMenuOpen((current) => !current)}
          >
            <Icon name={menuOpen ? "x" : "menu"} size={22} />
          </button>
        </div>
        {menuOpen && (
          <nav
            id="mobile-nav"
            aria-label="Mobile"
            className="border-t border-hairline bg-canvas md:hidden"
          >
            <div className="mx-auto flex w-full max-w-6xl flex-col gap-1 px-4 py-3">
              {signedIn ? (
                <>
                  {items.map((item) => (
                    <NavLink
                      key={item.to}
                      to={item.to}
                      className={mobileLinkClass}
                      onClick={closeMenu}
                    >
                      {item.label}
                    </NavLink>
                  ))}
                  <p className="px-2 py-1 text-sm text-steel">{user.email}</p>
                  <div className="pt-2">
                    <Button
                      variant="secondary"
                      pending={pending}
                      pendingLabel="Signing out…"
                      onClick={() => {
                        closeMenu();
                        void onLogout();
                      }}
                    >
                      Sign out
                    </Button>
                  </div>
                </>
              ) : status === "anonymous" ? (
                <>
                  <NavLink
                    to="/login"
                    className={mobileLinkClass}
                    onClick={closeMenu}
                  >
                    Sign in
                  </NavLink>
                  <NavLink
                    to="/register"
                    className={mobileLinkClass}
                    onClick={closeMenu}
                  >
                    Create an account
                  </NavLink>
                </>
              ) : null}
            </div>
          </nav>
        )}
      </header>
      <main id="main-content" className="flex-1">
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
      <footer className="border-t border-hairline bg-surface">
        <div className="cmyk-stripe h-1 w-full" aria-hidden="true" />
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 px-4 py-8 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex max-w-md flex-col gap-1">
            <p className="font-display text-sm font-bold text-ink">
              Smart Printing Network
            </p>
            <p className="text-sm text-steel">
              Upload a PDF, compare verified print shops, and collect your
              prints with a pickup code.
            </p>
          </div>
          <nav aria-label="Footer" className="flex flex-wrap gap-x-5 gap-y-2">
            <Link
              to="/new"
              onClick={closeMenu}
              className="inline-flex min-h-11 items-center text-sm text-ink transition-colors duration-150 hover:text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              New order
            </Link>
            <Link
              to="/register?as=shop"
              onClick={closeMenu}
              className="inline-flex min-h-11 items-center text-sm text-ink transition-colors duration-150 hover:text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              For print shops
            </Link>
            <a
              href={GITHUB_URL}
              target="_blank"
              rel="noreferrer"
              className="inline-flex min-h-11 items-center text-sm text-ink transition-colors duration-150 hover:text-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
            >
              GitHub
            </a>
          </nav>
        </div>
      </footer>
    </div>
  );
}
