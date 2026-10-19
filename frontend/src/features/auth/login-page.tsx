import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useLocation, useNavigate } from "react-router";

import { Alert, Button, TextField } from "../../components/ui";
import { fieldErrorsFor, messageForError } from "../../lib/errors";
import { loginSchema, type LoginValues } from "./schemas";
import { useSession } from "./session";

type LocationState = { registered?: boolean; from?: string } | null;

export function LoginPage() {
  const { login } = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const state = location.state as LocationState;
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
      const fallback =
        state?.from ?? (user.role === "vendor" ? "/vendor/rates" : "/");
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
    <section className="mx-auto flex w-full max-w-md flex-col gap-6 p-6">
      <h1 className="text-2xl font-semibold text-ink">Sign in</h1>
      {state?.registered === true && (
        <Alert variant="success">Account created. Sign in to continue.</Alert>
      )}
      {serverError !== null && <Alert>{serverError}</Alert>}
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          error={errors.email?.message}
          {...register("email")}
        />
        <TextField
          label="Password"
          type="password"
          autoComplete="current-password"
          error={errors.password?.message}
          {...register("password")}
        />
        <Button type="submit" pending={pending} pendingLabel="Signing in…">
          Sign in
        </Button>
      </form>
      <p className="text-sm text-steel">
        New customer?{" "}
        <Link className="text-primary underline" to="/register">
          Create an account
        </Link>
      </p>
      <p className="text-sm text-steel">
        Run a print shop?{" "}
        <Link className="text-primary underline" to="/register-vendor">
          Register your shop
        </Link>
      </p>
    </section>
  );
}
