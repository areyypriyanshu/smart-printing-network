import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router";

import { Alert, Button, TextField } from "../../components/ui";
import { fieldErrorsFor, messageForError } from "../../lib/errors";
import { registerRequest } from "./api";
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
      await registerRequest(values);
      void navigate("/login", { replace: true, state: { registered: true } });
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
    <section className="mx-auto flex w-full max-w-md flex-col gap-6 p-6">
      <h1 className="text-2xl font-semibold text-ink">Create your account</h1>
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
        <TextField
          label="Password"
          type="password"
          autoComplete="new-password"
          error={errors.password?.message}
          {...register("password")}
        />
        <Button
          type="submit"
          pending={pending}
          pendingLabel="Creating account…"
        >
          Create account
        </Button>
      </form>
      <p className="text-sm text-steel">
        Already have an account?{" "}
        <Link className="text-primary underline" to="/login">
          Sign in
        </Link>
      </p>
    </section>
  );
}
