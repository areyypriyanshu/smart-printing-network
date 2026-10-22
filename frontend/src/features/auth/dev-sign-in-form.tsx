import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useNavigate, useSearchParams } from "react-router";
import { z } from "zod";

import { Alert, Button, TextField } from "../../components/ui";
import { messageForError } from "../../lib/errors";
import { useDevAuth } from "./dev-session";
import { intentFromQuery, SHOP } from "./intent";

/**
 * The local way in, for the end to end suite.
 *
 * There is no password, because there is no password any more. The
 * account is a local one, and the only thing this proves is that the
 * application reads a session the way it always did.
 *
 * A person who came to register their shop is asked for the shop, the
 * same way the real sign up is, so that the suite walks the same path
 * a person walks.
 */
const schema = z.object({
  email: z.email("Enter a valid email address"),
  shop_name: z.string().trim().max(200, "Too long"),
  shop_address: z.string().trim().max(500, "Too long"),
  latitude: z.string().trim(),
  longitude: z.string().trim(),
});

type Values = z.infer<typeof schema>;

export function DevSignInForm() {
  const { signIn } = useDevAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [search] = useSearchParams();
  // The reason is in the address of the link, which is where the
  // person came from. It is read here and not from the browser's
  // storage, because the storage is filled in after this page is
  // drawn and the shop's fields have to be there in the first one.
  const isShop = intentFromQuery(search.get("as")) === SHOP;
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      email: "",
      shop_name: "",
      shop_address: "",
      latitude: "",
      longitude: "",
    },
  });

  const onSubmit = handleSubmit(async (values) => {
    setError(null);
    try {
      await signIn({
        email: values.email,
        role: isShop ? "vendor" : "customer",
        ...(isShop
          ? {
              shop_name: values.shop_name,
              shop_address: values.shop_address,
              latitude: Number(values.latitude),
              longitude: Number(values.longitude),
            }
          : {}),
      });
      // The session is held now, so the page a person came to leave
      // is not the page they should be on.
      navigate("/", { replace: true });
    } catch (caught) {
      setError(messageForError(caught));
    }
  });

  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(event) => void onSubmit(event)}
    >
      <TextField
        label="Email"
        type="email"
        error={errors.email?.message}
        {...register("email")}
      />
      {isShop && (
        <>
          <TextField
            label="Shop name"
            error={errors.shop_name?.message}
            {...register("shop_name")}
          />
          <TextField
            label="Shop address"
            error={errors.shop_address?.message}
            {...register("shop_address")}
          />
          <TextField
            label="Latitude"
            error={errors.latitude?.message}
            {...register("latitude")}
          />
          <TextField
            label="Longitude"
            error={errors.longitude?.message}
            {...register("longitude")}
          />
        </>
      )}
      {error !== null && <Alert variant="error">{error}</Alert>}
      <Button type="submit" pending={isSubmitting} pendingLabel="Signing in…">
        Sign in
      </Button>
    </form>
  );
}
