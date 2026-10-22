import { zodResolver } from "@hookform/resolvers/zod";
import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { useNavigate } from "react-router";

import { Alert, Button, TextField, Textarea } from "../../components/ui";
import { messageForError } from "../../lib/errors";
import { onboardRequest } from "./api";
import { AuthLayout } from "./auth-layout";
import { forgetIntent, readIntent, SHOP } from "./intent";
import { onboardingSchema, type OnboardingValues } from "./onboarding-schemas";
import { useSession } from "./session";

/**
 * The one question a person has to answer before anything else works.
 *
 * The role is fixed here, for good. A customer who later decides to
 * run a shop needs a separate account, because a shop's history
 * belongs to the shop and a customer's history belongs to the customer.
 *
 * A person who came to register their shop is not asked. They followed
 * the link that says so, and the only thing they are asked for is the
 * shop itself.
 */
export function OnboardingPage() {
  const { refreshUser } = useSession();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [intent, setIntent] = useState(readIntent);
  const isShop = intent === SHOP;
  const {
    register,
    handleSubmit,
    control,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<OnboardingValues>({
    resolver: zodResolver(onboardingSchema),
    defaultValues: {
      role: isShop ? "vendor" : "customer",
      shop_name: "",
      shop_address: "",
      phone: "",
      latitude: "",
      longitude: "",
    },
  });

  const chosen = useWatch({ control, name: "role" });
  const role = isShop ? "vendor" : chosen;

  /**
   * The person is here to print something after all.
   *
   * The link that sent them here said they were registering a shop, and
   * they can say otherwise. The reason is dropped, so it cannot follow
   * them to the next account.
   */
  const printInstead = () => {
    forgetIntent();
    setIntent(null);
    setValue("role", "customer");
  };

  const onSubmit = handleSubmit(async (values) => {
    setError(null);
    // The coordinates are optional. A shop owner who knows them types
    // them, and one who does not lets the address be looked up.
    const hasCoordinates =
      values.latitude.trim() !== "" && values.longitude.trim() !== "";
    try {
      await onboardRequest({
        role: values.role,
        ...(values.role === "vendor"
          ? {
              shop_name: values.shop_name,
              shop_address: values.shop_address,
              phone:
                values.phone === undefined || values.phone === ""
                  ? null
                  : values.phone,
              ...(hasCoordinates
                ? {
                    latitude: Number(values.latitude),
                    longitude: Number(values.longitude),
                  }
                : {}),
            }
          : {}),
      });
      forgetIntent();
      await refreshUser();
      navigate("/", { replace: true });
    } catch (caught) {
      setError(messageForError(caught));
    }
  });

  return (
    <AuthLayout
      title={isShop ? "Set up your shop" : "What are you here for?"}
      subtitle={
        isShop
          ? "The shop waits for the team to look at it before it takes orders."
          : "This decides what the account can do, and it does not change later."
      }
    >
      <form
        className="flex flex-col gap-5"
        onSubmit={(event) => void onSubmit(event)}
      >
        {!isShop && (
          <fieldset className="flex flex-col gap-2">
            <legend className="text-sm font-medium text-ink">
              I am here to
            </legend>
            <label className="flex items-center gap-2 text-sm text-ink">
              <input
                type="radio"
                value="customer"
                {...register("role")}
                className="size-4"
              />
              Print something
            </label>
            <label className="flex items-center gap-2 text-sm text-ink">
              <input
                type="radio"
                value="vendor"
                {...register("role")}
                className="size-4"
              />
              Run a print shop
            </label>
          </fieldset>
        )}

        {role === "vendor" && (
          <div className="flex flex-col gap-4">
            <TextField
              label="Shop name"
              error={errors.shop_name?.message}
              {...register("shop_name")}
            />
            <div className="flex flex-col gap-1.5">
              <label
                htmlFor="shop_address"
                className="text-sm font-medium text-ink"
              >
                Shop address
              </label>
              <Textarea
                id="shop_address"
                rows={2}
                aria-invalid={errors.shop_address !== undefined}
                {...register("shop_address")}
              />
              {errors.shop_address !== undefined && (
                <p role="alert" className="text-sm text-danger">
                  {errors.shop_address.message}
                </p>
              )}
            </div>
            <TextField
              label="Phone (optional)"
              type="tel"
              error={errors.phone?.message}
              {...register("phone")}
            />
            <TextField
              label="Latitude (optional)"
              error={errors.latitude?.message}
              {...register("latitude")}
            />
            <TextField
              label="Longitude (optional)"
              error={errors.longitude?.message}
              {...register("longitude")}
            />
            <p className="text-xs text-steel">
              Leave the coordinates empty and we will look the address up on the
              map. If your deployment cannot do that, the coordinates are
              needed.
            </p>
          </div>
        )}

        {error !== null && <Alert variant="error">{error}</Alert>}

        <Button type="submit" pending={isSubmitting} pendingLabel="Setting up…">
          {isShop ? "Set up my shop" : "Continue"}
        </Button>

        {isShop && (
          <button
            type="button"
            onClick={printInstead}
            className="self-start text-sm text-steel underline underline-offset-4 hover:text-ink"
          >
            I am here to print something instead
          </button>
        )}
      </form>
    </AuthLayout>
  );
}
