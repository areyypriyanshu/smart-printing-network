import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ApiError } from "../../api/client";
import { Alert, Button, Input, TextField } from "../../components/ui";
import { messageForError } from "../../lib/errors";
import { isValidRupeesInput, parseRupeesToPaise } from "../../lib/money";
import { useUpdateVendorShop, useVendorShop } from "./api";

const settingsSchema = z.object({
  name: z.string().trim().min(1, "Enter the shop name").max(200, "Too long"),
  minOrderRupees: z
    .string()
    .refine(
      (value) => value.trim() === "" || isValidRupeesInput(value),
      "Enter a positive amount like 50",
    ),
  acceptingOrders: z.boolean(),
});

type SettingsValues = z.infer<typeof settingsSchema>;

export function VendorSettingsPage() {
  const shop = useVendorShop();
  const updateShop = useUpdateVendorShop();
  const [serverError, setServerError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<SettingsValues>({
    resolver: zodResolver(settingsSchema),
    defaultValues: { name: "", minOrderRupees: "", acceptingOrders: true },
  });

  useEffect(() => {
    if (shop.data !== undefined) {
      reset({
        name: shop.data.name,
        minOrderRupees:
          shop.data.min_order_paise === 0
            ? ""
            : String(shop.data.min_order_paise / 100),
        acceptingOrders: shop.data.accepting_orders,
      });
    }
  }, [shop.data, reset]);

  const onSubmit = handleSubmit(async (values) => {
    setServerError(null);
    setSaved(false);
    const minOrderPaise =
      values.minOrderRupees.trim() === ""
        ? 0
        : (parseRupeesToPaise(values.minOrderRupees) ?? 0);
    try {
      await updateShop.mutateAsync({
        name: values.name,
        min_order_paise: minOrderPaise,
        accepting_orders: values.acceptingOrders,
      });
      setSaved(true);
    } catch (error) {
      setServerError(messageForError(error));
    }
  });

  if (shop.isPending) {
    return (
      <p role="status" className="p-6 text-steel">
        Loading your shop…
      </p>
    );
  }

  if (shop.error instanceof ApiError && shop.error.code === "NOT_FOUND") {
    return (
      <section className="mx-auto flex w-full max-w-2xl flex-col gap-3 p-6">
        <h1 className="text-2xl font-semibold text-ink">Shop settings</h1>
        <p className="text-steel">
          This account does not have a shop yet. Register a shop to manage it
          here.
        </p>
      </section>
    );
  }

  if (shop.isError) {
    return (
      <section className="mx-auto flex w-full max-w-2xl flex-col gap-3 p-6">
        <h1 className="text-2xl font-semibold text-ink">Shop settings</h1>
        <Alert>{messageForError(shop.error)}</Alert>
        <Button variant="secondary" onClick={() => void shop.refetch()}>
          Try again
        </Button>
      </section>
    );
  }

  return (
    <section className="mx-auto flex w-full max-w-2xl flex-col gap-6 p-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold text-ink">Shop settings</h1>
        <p className="text-steel">
          Keep your shop details and order limits up to date.
        </p>
      </div>
      {!shop.data.is_verified && (
        <Alert variant="info">
          Your shop is not verified yet. Customers will see it after our team
          reviews it.
        </Alert>
      )}
      {saved && <Alert variant="success">Shop saved.</Alert>}
      {serverError !== null && <Alert>{serverError}</Alert>}
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
        <TextField
          label="Shop name"
          error={errors.name?.message}
          {...register("name")}
        />
        <p className="text-sm text-steel">{shop.data.address}</p>
        <TextField
          label="Minimum order (₹, optional)"
          inputMode="decimal"
          error={errors.minOrderRupees?.message}
          {...register("minOrderRupees")}
        />
        <div className="flex items-center gap-2">
          <Input
            id="acceptingOrders"
            type="checkbox"
            className="h-5 w-5 accent-primary"
            aria-describedby="acceptingOrders-hint"
            {...register("acceptingOrders")}
          />
          <label htmlFor="acceptingOrders" className="text-sm text-ink">
            Accepting new orders
          </label>
        </div>
        <p id="acceptingOrders-hint" className="text-sm text-steel">
          Turn this off to hide your shop from new orders.
        </p>
        <div>
          <Button
            type="submit"
            pending={updateShop.isPending}
            pendingLabel="Saving…"
          >
            Save shop
          </Button>
        </div>
      </form>
    </section>
  );
}
