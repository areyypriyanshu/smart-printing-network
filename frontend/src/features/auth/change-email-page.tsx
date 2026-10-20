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
import { AuthLayout } from "./auth-layout";
import { changeEmailRequest } from "./api";
import { changeEmailSchema, type ChangeEmailValues } from "./schemas";
import { useSession } from "./session";

/**
 * Putting a different address on the account.
 *
 * This is the way out of a mistyped address. Without it, an account
 * made with an address nobody can read can never be proved, and the
 * address it holds can never be used by the person it belongs to.
 */
export function ChangeEmailPage() {
  const { user, refreshUser } = useSession();
  const navigate = useNavigate();
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<ChangeEmailValues>({ resolver: zodResolver(changeEmailSchema) });

  const onSubmit = handleSubmit(async (values) => {
    setPending(true);
    setServerError(null);
    try {
      await changeEmailRequest(values);
      await refreshUser();
      void navigate("/account/email", {
        replace: true,
        state: { changed: true },
      });
    } catch (error) {
      const fields = fieldErrorsFor(error);
      const names = Object.keys(fields) as Array<keyof ChangeEmailValues>;
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
      title="Email address"
      subtitle="The address we send your orders and your pickup code to."
      footer={
        <p className="border-t border-hairline pt-6 text-sm text-steel">
          <Link className={linkClassName()} to="/">
            Back to the shop
          </Link>
        </p>
      }
    >
      {user !== null && (
        <p className="text-sm text-steel">
          This account uses <strong>{user.email}</strong>.
        </p>
      )}
      {serverError !== null && <Alert>{serverError}</Alert>}
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <TextField
          label="New email address"
          type="email"
          autoComplete="email"
          error={errors.email?.message}
          {...register("email")}
        />
        <PasswordField
          label="Your password"
          autoComplete="current-password"
          error={errors.password?.message}
          {...register("password")}
        />
        <Button type="submit" pending={pending} pendingLabel="Saving…">
          Change the address
        </Button>
      </form>
    </AuthLayout>
  );
}
