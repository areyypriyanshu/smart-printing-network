import { Link } from "react-router";

export function ForbiddenPage() {
  return (
    <section className="mx-auto flex w-full max-w-md flex-col gap-3 p-6">
      <h1 className="text-2xl font-semibold text-ink">Not allowed</h1>
      <p className="text-steel">
        Your account does not have access to this page.
      </p>
      <Link className="text-primary underline" to="/">
        Back to home
      </Link>
    </section>
  );
}

export function NotFoundPage() {
  return (
    <section className="mx-auto flex w-full max-w-md flex-col gap-3 p-6">
      <h1 className="text-2xl font-semibold text-ink">Page not found</h1>
      <p className="text-steel">The page you asked for does not exist.</p>
      <Link className="text-primary underline" to="/">
        Back to home
      </Link>
    </section>
  );
}
