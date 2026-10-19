import { Link } from "react-router";

import { useSession } from "../auth";

export function HomePage() {
  const { status, user } = useSession();

  if (status === "loading") {
    return (
      <p role="status" className="p-6 text-steel">
        Loading…
      </p>
    );
  }

  if (status === "anonymous" || user === null) {
    return (
      <section className="mx-auto flex w-full max-w-2xl flex-col gap-4 p-6">
        <h1 className="text-3xl font-semibold text-ink">
          Print from a shop near you
        </h1>
        <p className="text-steel">
          Upload a PDF, choose your print options, pay online and collect it
          from a verified print shop with a pickup code.
        </p>
        <div className="flex flex-wrap gap-3">
          <Link
            to="/register"
            className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-deep"
          >
            Create an account
          </Link>
          <Link
            to="/login"
            className="inline-flex min-h-11 items-center rounded-md border border-hairline-strong bg-canvas px-4 py-2 text-sm font-medium text-ink hover:bg-surface"
          >
            Sign in
          </Link>
        </div>
      </section>
    );
  }

  if (user.role === "vendor") {
    return (
      <section className="mx-auto flex w-full max-w-2xl flex-col gap-4 p-6">
        <h1 className="text-3xl font-semibold text-ink">
          Welcome, {user.full_name}
        </h1>
        <p className="text-steel">
          Set your rates so customers can see your prices, and keep your shop
          details up to date.
        </p>
        <div className="flex flex-wrap gap-3">
          <Link className="text-primary underline" to="/vendor/rates">
            Manage rates
          </Link>
          <Link className="text-primary underline" to="/vendor/settings">
            Shop settings
          </Link>
        </div>
      </section>
    );
  }

  return (
    <section className="mx-auto flex w-full max-w-2xl flex-col gap-4 p-6">
      <h1 className="text-3xl font-semibold text-ink">
        Welcome, {user.full_name}
      </h1>
      <p className="text-steel">
        Upload a PDF, choose your print options, and compare prices from
        verified shops near you.
      </p>
      <div>
        <Link
          to="/new"
          className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-deep"
        >
          Start a new order
        </Link>
      </div>
    </section>
  );
}
