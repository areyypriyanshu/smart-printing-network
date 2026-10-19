import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router";

import { Alert, Button, TextField } from "../../components/ui";
import { fieldErrorsFor, messageForError } from "../../lib/errors";
import { registerVendorRequest } from "./api";
import { registerVendorSchema, type RegisterVendorValues } from "./schemas";

export function RegisterVendorPage() {
  const navigate = useNavigate();
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<RegisterVendorValues>({
    resolver: zodResolver(registerVendorSchema),
  });

  const onSubmit = handleSubmit(async (values) => {
    setPending(true);
    setServerError(null);
    try {
      await registerVendorRequest({
        email: values.email,
        full_name: values.full_name,
        password: values.password,
        shop_name: values.shop_name,
        shop_address: values.shop_address,
        latitude: Number(values.latitude),
        longitude: Number(values.longitude),
      });
      void navigate("/login", { replace: true, state: { registered: true } });
    } catch (error) {
      const fields = fieldErrorsFor(error);
      const names = Object.keys(fields) as Array<keyof RegisterVendorValues>;
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
      <h1 className="text-2xl font-semibold text-ink">
        Register your print shop
      </h1>
      <p className="text-sm text-steel">
        Create a vendor account and your shop profile. One of our team members
        verifies new shops before customers can find them.
      </p>
      {serverError !== null && <Alert>{serverError}</Alert>}
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <TextField
          label="Shop name"
          autoComplete="organization"
          error={errors.shop_name?.message}
          {...register("shop_name")}
        />
        <TextField
          label="Shop address"
          autoComplete="street-address"
          error={errors.shop_address?.message}
          {...register("shop_address")}
        />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <TextField
            label="Latitude"
            inputMode="decimal"
            error={errors.latitude?.message}
            {...register("latitude")}
          />
          <TextField
            label="Longitude"
            inputMode="decimal"
            error={errors.longitude?.message}
            {...register("longitude")}
          />
        </div>
        <TextField
          label="Your name"
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
          Register shop
        </Button>
      </form>
      <p className="text-sm text-steel">
        Just here to print?{" "}
        <Link className="text-primary underline" to="/register">
          Create a customer account
        </Link>
      </p>
    </section>
  );
}
