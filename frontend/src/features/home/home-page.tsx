import { Link } from "react-router";

import { useSession } from "../auth";

export function HomePage() {
  const { status, user } = useSession();

  if (status === "loading") {
    return (
      <p role="status" className="p-6 text-slate-600">
        Loading…
      </p>
    );
  }

  if (status === "anonymous" || user === null) {
    return (
      <section className="mx-auto flex w-full max-w-2xl flex-col gap-4 p-6">
        <h1 className="text-3xl font-semibold text-slate-900">
          Print from a shop near you
        </h1>
        <p className="text-slate-700">
          Upload a PDF, choose your print options, pay online and collect it
          from a verified print shop with a pickup code.
        </p>
        <div className="flex flex-wrap gap-3">
          <Link
            to="/register"
            className="inline-flex min-h-11 items-center rounded-md bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700"
          >
            Create an account
          </Link>
          <Link
            to="/login"
            className="inline-flex min-h-11 items-center rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
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
        <h1 className="text-3xl font-semibold text-slate-900">
          Welcome, {user.full_name}
        </h1>
        <p className="text-slate-700">
          Set your rates so customers can see your prices, and keep your shop
          details up to date.
        </p>
        <div className="flex flex-wrap gap-3">
          <Link className="text-primary-600 underline" to="/vendor/rates">
            Manage rates
          </Link>
          <Link className="text-primary-600 underline" to="/vendor/settings">
            Shop settings
          </Link>
        </div>
      </section>
    );
  }

  return (
    <section className="mx-auto flex w-full max-w-2xl flex-col gap-4 p-6">
      <h1 className="text-3xl font-semibold text-slate-900">
        Welcome, {user.full_name}
      </h1>
      <p className="text-slate-700">
        You are signed in. PDF upload and ordering arrive with the next
        milestone of the project.
      </p>
    </section>
  );
}
