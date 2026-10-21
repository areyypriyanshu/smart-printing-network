import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router";

import {
  Alert,
  Button,
  linkClassName,
  PasswordField,
  TextField,
} from "../../components/ui";
import { fieldErrorsFor, messageForError } from "../../lib/errors";
import { registerRequest } from "./api";
import { AuthLayout } from "./auth-layout";
import { registerSchema, type RegisterValues } from "./schemas";

export function RegisterPage() {
  const navigate = useNavigate();
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<RegisterValues>({ resolver: zodResolver(registerSchema) });

  const onSubmit = handleSubmit(async (values) => {
    setPending(true);
    setServerError(null);
    try {
      const user = await registerRequest(values);
      // The account exists, and a link has been sent to the address.
      // The next screen says where it went, so that a customer who
      // mistyped it sees the mistake.
      void navigate("/check-your-email", {
        replace: true,
        state: { email: user.email },
      });
    } catch (error) {
      const fields = fieldErrorsFor(error);
      const names = Object.keys(fields) as Array<keyof RegisterValues>;
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
      title="Create an account"
      subtitle="Save your uploads and order prints in a few steps."
      footer={
        <p className="border-t border-hairline pt-6 text-sm text-steel">
          Already have an account?{" "}
          <Link className={linkClassName()} to="/login">
            Sign in
          </Link>
        </p>
      }
    >
      {serverError !== null && <Alert>{serverError}</Alert>}
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <TextField
          label="Full name"
          autoComplete="name"
          error={errors.full_name?.message}
          {...register("full_name")}
        />
        <TextField
          label="Email"
          type="email"
          autoComplete="email"
          error={errors.email?.message}
          {...register("email")}
        />
        <PasswordField
          label="Password"
          autoComplete="new-password"
          error={errors.password?.message}
          {...register("password")}
        />
        <Button
          type="submit"
          pending={pending}
          pendingLabel="Creating account…"
        >
          Create an account
        </Button>
      </form>
    </AuthLayout>
  );
}
