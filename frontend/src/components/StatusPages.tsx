import { Link } from "react-router";

export function ForbiddenPage() {
  return (
    <section className="mx-auto flex w-full max-w-md flex-col gap-3 p-6">
      <h1 className="text-2xl font-semibold text-slate-900">Not allowed</h1>
      <p className="text-slate-700">
        Your account does not have access to this page.
      </p>
      <Link className="text-primary-600 underline" to="/">
        Back to home
      </Link>
    </section>
  );
}

export function NotFoundPage() {
  return (
    <section className="mx-auto flex w-full max-w-md flex-col gap-3 p-6">
      <h1 className="text-2xl font-semibold text-slate-900">Page not found</h1>
      <p className="text-slate-700">The page you asked for does not exist.</p>
      <Link className="text-primary-600 underline" to="/">
        Back to home
      </Link>
    </section>
  );
}
