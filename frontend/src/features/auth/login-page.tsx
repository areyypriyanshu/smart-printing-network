import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router";

import {
  Alert,
  Button,
  linkClassName,
  PasswordField,
  TextField,
} from "../../components/ui";
import type { Role } from "../../api/client";
import {
  fieldErrorsFor,
  messageForCode,
  messageForError,
} from "../../lib/errors";
import { AuthLayout } from "./auth-layout";
import { GoogleButton } from "./google-button";
import { loginSchema, type LoginValues } from "./schemas";
import { useSession } from "./session";
import { useOAuthProviders } from "./use-oauth-providers";

type LocationState = { registered?: boolean; from?: string } | null;

/**
 * Where each role lands after signing in.
 *
 * An admin who lands on the customer home page has to hunt for the link
 * to the panel, and a vendor who lands on it is shown a call to action
 * to order a printout, which is not their shop. The landing page is the
 * one screen the role is known from, so it should be the right one.
 */
const ROLE_HOME: Record<Role, string> = {
  customer: "/",
  vendor: "/vendor/rates",
  admin: "/admin/shops",
};

export function LoginPage() {
  const { login } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const state = location.state as LocationState;
  const [searchParams] = useSearchParams();
  const providers = useOAuthProviders();
  // A sign in with a provider that did not work sends the browser back
  // here with the reason in the address.
  const oauthError = searchParams.get("oauth_error");
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<LoginValues>({ resolver: zodResolver(loginSchema) });

  const onSubmit = handleSubmit(async (values) => {
    setPending(true);
    setServerError(null);
    try {
      const user = await login(values.email, values.password);
      const fallback = state?.from ?? ROLE_HOME[user.role];
      void navigate(fallback, { replace: true });
    } catch (error) {
      const fields = fieldErrorsFor(error);
      const names = Object.keys(fields) as Array<keyof LoginValues>;
      if (names.length > 0) {
        for (const name of names) setError(name, { message: fields[name] });
      } else {
        setServerError(messageForError(error));
      }
    } finally {
      setPending(false);
    }
  });

  return (
    <AuthLayout
      title="Sign in"
      subtitle="Order prints from verified shops near you."
      footer={
        <div className="flex flex-col gap-2 border-t border-hairline pt-6">
          <p className="text-sm text-steel">
            New customer?{" "}
            <Link className={linkClassName()} to="/register">
              Create an account
            </Link>
          </p>
          <p className="text-sm text-steel">
            Run a print shop?{" "}
            <Link className={linkClassName()} to="/register-vendor">
              Register your shop
            </Link>
          </p>
        </div>
      }
    >
      {state?.registered === true && (
        <Alert variant="success">Account created. Sign in to continue.</Alert>
      )}
      {oauthError !== null && <Alert>{messageForCode(oauthError)}</Alert>}
      {serverError !== null && <Alert>{serverError}</Alert>}
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          error={errors.email?.message}
          {...register("email")}
        />
        <PasswordField
          label="Password"
          autoComplete="current-password"
          error={errors.password?.message}
          {...register("password")}
        />
        <Button type="submit" pending={pending} pendingLabel="Signing in…">
          Sign in
        </Button>
      </form>
      {providers.includes("google") && (
        <div className="flex flex-col gap-2">
          <GoogleButton />
          <p className="text-xs text-steel">
            Google tells us your email address is proved, so you can order a
            print straight away.
          </p>
        </div>
      )}
    </AuthLayout>
  );
}
