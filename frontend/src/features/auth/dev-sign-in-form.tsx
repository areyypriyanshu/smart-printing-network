import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate } from "react-router";
import { z } from "zod";

import { Alert, Button, TextField } from "../../components/ui";
import { messageForError } from "../../lib/errors";
import { useDevAuth } from "./dev-session";

/**
 * The local way in, for the end to end suite.
 *
 * There is no password, because there is no password any more. The
 * account is a local one, and the only thing this proves is that the
 * application reads a session the way it always did.
 */
const schema = z.object({
  email: z.email("Enter a valid email address"),
});

type Values = z.infer<typeof schema>;

export function DevSignInForm() {
  const { signIn } = useDevAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Values>({ resolver: zodResolver(schema) });

  const onSubmit = handleSubmit(async (values) => {
    setError(null);
    try {
      await signIn(values.email);
      // The session is held now, so the page a person came to leave
      // is not the page they should be on.
      navigate("/", { replace: true });
    } catch (caught) {
      setError(messageForError(caught));
    }
  });

  return (
    <form className="flex flex-col gap-4" onSubmit={(event) => void onSubmit(event)}>
      <TextField
        label="Email"
        type="email"
        error={errors.email?.message}
        {...register("email")}
      />
      {error !== null && <Alert variant="error">{error}</Alert>}
      <Button type="submit" pending={isSubmitting} pendingLabel="Signing in…">
        Sign in
      </Button>
    </form>
  );
}
