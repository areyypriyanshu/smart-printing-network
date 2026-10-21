import { SignIn } from "@clerk/react";

import { AuthLayout } from "./auth-layout";
import { DevSignInForm } from "./dev-sign-in-form";

/**
 * The way in.
 *
 * The sign-in is the identity provider's, because the provider holds
 * the password and the proof of the address. The application asks for
 * neither.
 *
 * The local stand-in is for the end to end suite, which has to run
 * offline. It is chosen by a build-time setting that a deployment
 * never has.
 */
export function SignInPage() {
  if (import.meta.env.VITE_SPN_DEV_AUTH === "true") {
    return (
      <AuthLayout
        title="Sign in"
        subtitle="Use the address the account was made with."
      >
        <DevSignInForm />
      </AuthLayout>
    );
  }
  return (
    <AuthLayout
      title="Sign in"
      subtitle="Your address and your password are held by our identity provider."
    >
      <div className="flex justify-center">
        <SignIn fallbackRedirectUrl="/" />
      </div>
    </AuthLayout>
  );
}
