import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router";

import {
  Alert,
  Button,
  PasswordField,
  Stepper,
  TextField,
} from "../../components/ui";
import { fieldErrorsFor, messageForError } from "../../lib/errors";
import { registerVendorRequest } from "./api";
import { AuthLayout } from "./auth-layout";
import { registerVendorSchema, type RegisterVendorValues } from "./schemas";

const STEPS = ["Shop", "Location", "Account"];

const STEP_FIELDS: ReadonlyArray<ReadonlyArray<keyof RegisterVendorValues>> = [
  ["shop_name", "shop_address"],
  ["latitude", "longitude"],
  ["full_name", "email", "password"],
];

export function RegisterVendorPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [serverError, setServerError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const {
    register,
    handleSubmit,
    setError,
    trigger,
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
        const firstStep = STEP_FIELDS.findIndex((fieldsInStep) =>
          fieldsInStep.some((field) => names.includes(field)),
        );
        if (firstStep >= 0) setStep(firstStep);
      } else {
        setServerError(messageForError(error));
      }
    } finally {
      setPending(false);
    }
  });

  const onContinue = async () => {
    const valid = await trigger([...STEP_FIELDS[step]]);
    if (valid) setStep((current) => Math.min(current + 1, STEPS.length - 1));
  };

  return (
    <AuthLayout
      title="Register your print shop"
      subtitle="Create a vendor account and your shop profile. Our team verifies new shops before customers can find them."
      footer={
        <p className="border-t border-hairline pt-6 text-sm text-steel">
          Just here to print?{" "}
          <Link
            className="font-medium text-primary underline underline-offset-2 hover:text-primary-deep"
            to="/register"
          >
            Create a customer account
          </Link>
        </p>
      }
    >
      {serverError !== null && <Alert>{serverError}</Alert>}
      <Stepper steps={STEPS} current={step + 1} />
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        {step === 0 && (
          <>
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
            <p className="text-sm text-steel">
              Customers use this to recognise your shop at pickup.
            </p>
          </>
        )}
        {step === 1 && (
          <>
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
            <p className="text-sm text-steel">
              Paste the coordinates from Google Maps. They decide which nearby
              customers see your shop.
            </p>
          </>
        )}
        {step === 2 && (
          <>
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
            <PasswordField
              label="Password"
              autoComplete="new-password"
              error={errors.password?.message}
              {...register("password")}
            />
          </>
        )}
        <div className="flex flex-wrap gap-3">
          {step > 0 && (
            <Button
              type="button"
              variant="secondary"
              onClick={() => setStep((current) => current - 1)}
            >
              Back
            </Button>
          )}
          {step < STEPS.length - 1 ? (
            <Button type="button" onClick={() => void onContinue()}>
              Continue
            </Button>
          ) : (
            <Button
              type="submit"
              pending={pending}
              pendingLabel="Creating account…"
            >
              Register shop
            </Button>
          )}
        </div>
      </form>
    </AuthLayout>
  );
}
