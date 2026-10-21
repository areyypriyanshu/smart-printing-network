import { SignUp } from "@clerk/react";

import { AuthLayout } from "./auth-layout";
import { DevSignInForm } from "./dev-sign-in-form";

/**
 * The way to an account.
 *
 * The sign-up is the identity provider's, because the provider holds
 * the password and sends the message that proves the address. The
 * application asks for neither, and never sees a password at all.
 */
export function SignUpPage() {
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
