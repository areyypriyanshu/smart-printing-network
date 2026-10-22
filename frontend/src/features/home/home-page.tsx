import { Link } from "react-router";

import {
  buttonClassName,
  linkClassName,
  pageTitleClassName,
} from "../../components/ui";
import { useSession } from "../auth";
import { LandingPage } from "./landing-page";

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
    return <LandingPage />;
  }

  if (user.role === "vendor") {
    return (
      <section className="mx-auto flex w-full max-w-2xl flex-col gap-4 p-6">
        <h1 className={pageTitleClassName()}>Welcome, {user.full_name}</h1>
        <p className="text-steel">
          Work the order queue, set your rates so customers can see your prices,
          and keep your shop details up to date.
        </p>
        <div className="flex flex-wrap gap-3">
          <Link className={linkClassName()} to="/vendor">
            Open the queue
          </Link>
          <Link className={linkClassName()} to="/vendor/rates">
            Manage rates
          </Link>
          <Link className={linkClassName()} to="/vendor/settings">
            Shop settings
          </Link>
        </div>
      </section>
    );
  }

  return (
    <section className="mx-auto flex w-full max-w-2xl flex-col gap-4 p-6">
      <h1 className={pageTitleClassName()}>Welcome, {user.full_name}</h1>
      <p className="text-steel">
        Upload a PDF, choose your print options, and compare prices from
        verified shops near you.
      </p>
      <div className="flex flex-wrap gap-3">
        <Link to="/new" className={buttonClassName("primary")}>
          Start a new order
        </Link>
        <Link to="/shops" className={buttonClassName("secondary")}>
          Find a shop near you
        </Link>
      </div>
    </section>
  );
}
