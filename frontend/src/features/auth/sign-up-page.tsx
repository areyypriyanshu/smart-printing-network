import { SignUp } from "@clerk/react";
import { useEffect } from "react";
import { useSearchParams } from "react-router";

import { AuthLayout } from "./auth-layout";
import { DevSignInForm } from "./dev-sign-in-form";
import { intentFromQuery, rememberIntent } from "./intent";

/**
 * The way to an account.
 *
 * The sign-up is the identity provider's, because the provider holds
 * the password and sends the message that proves the address. The
 * application asks for neither, and never sees a password at all.
 *
 * A person who followed the link that says "register your shop" has
 * already said what they are here for, and the address carries it. It
 * is kept here, because the provider's sign up happens in between and
 * the reason has to survive the trip.
 */
export function SignUpPage() {
  const [search] = useSearchParams();

  useEffect(() => {
    const intent = intentFromQuery(search.get("as"));
    if (intent !== null) rememberIntent(intent);
  }, [search]);

  if (import.meta.env.VITE_SPN_DEV_AUTH === "true") {
    return (
      <AuthLayout
        title="Create an account"
        subtitle="Use the address you want the account to be made with."
      >
        <DevSignInForm />
      </AuthLayout>
    );
  }
  return (
    <AuthLayout
      title="Create an account"
      subtitle="Your address and your password are held by our identity provider."
    >
      <div className="flex justify-center">
        <SignUp fallbackRedirectUrl="/" />
      </div>
    </AuthLayout>
  );
}
