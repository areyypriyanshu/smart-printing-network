import { Link, useLocation } from "react-router";

import { linkClassName } from "../../components/ui";
import { AuthLayout } from "./auth-layout";

type LocationState = { email?: string } | null;

/**
 * The page a new customer is sent to after signing up.
 *
 * It says where the link went, so that a customer who mistyped the
 * address sees the mistake before they wait for a message that will
 * never arrive. The link can be sent again once they are signed in,
 * and the account page can put a different address on the account.
 */
export function CheckEmailPage() {
  const location = useLocation();
  const state = location.state as LocationState;
  const email = state?.email ?? "";

  return (
    <AuthLayout
      title="Check your email"
      subtitle="One more step and you can order a print."
      footer={
        <div className="flex flex-col gap-2 border-t border-hairline pt-6">
          <p className="text-sm text-steel">
            Signed up with the wrong address?{" "}
            <Link className={linkClassName()} to="/account/email">
              Use a different email address
            </Link>
          </p>
          <p className="text-sm text-steel">
            Already confirmed?{" "}
            <Link className={linkClassName()} to="/login">
              Sign in
            </Link>
          </p>
        </div>
      }
    >
      {email !== "" ? (
        <p className="text-sm text-ink">
          We sent a link to <strong>{email}</strong>. Open it and your address
          is confirmed.
        </p>
      ) : (
        <p className="text-sm text-ink">
          We sent you a link. Open it and your address is confirmed.
        </p>
      )}
      <p className="text-sm text-steel">
        Nothing arrived? Sign in and we will send the link again.
      </p>
    </AuthLayout>
  );
}
