import { Link } from "react-router";

import { buttonClassName, pageTitleClassName } from "./ui";

export function ForbiddenPage() {
  return (
    <section className="mx-auto flex w-full max-w-md flex-col gap-3 p-6">
      <h1 className={pageTitleClassName()}>Not allowed</h1>
      <p className="text-steel">
        Your account does not have access to this page.
      </p>
      <div>
        <Link className={buttonClassName("secondary")} to="/">
          Back to home
        </Link>
      </div>
    </section>
  );
}

export function NotFoundPage() {
  return (
    <section className="mx-auto flex w-full max-w-md flex-col gap-3 p-6">
      <h1 className={pageTitleClassName()}>Page not found</h1>
      <p className="text-steel">The page you asked for does not exist.</p>
      <div>
        <Link className={buttonClassName("secondary")} to="/">
          Back to home
        </Link>
      </div>
    </section>
  );
}
