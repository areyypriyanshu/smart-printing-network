import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";

import { ApiError } from "../../api/client";
import { Alert, Button, Input } from "../../components/ui";
import { messageForError } from "../../lib/errors";
import { useVendorShop } from "../vendor-settings";
import { useReplaceVendorRates, useVendorRates } from "./api";
import {
  emptyRateRows,
  ratesSchema,
  rowLabel,
  rowsFromRateItems,
  rowsToFormValues,
  rowsToRateItems,
  type RatesFormValues,
} from "./rates";

export function VendorRatesPage() {
  const shop = useVendorShop();
  const rates = useVendorRates();
  const replaceRates = useReplaceVendorRates();
  const [serverError, setServerError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors },
  } = useForm<RatesFormValues>({
    resolver: zodResolver(ratesSchema),
    defaultValues: rowsToFormValues(emptyRateRows()),
  });

  useEffect(() => {
    if (rates.data !== undefined) {
      reset(rowsToFormValues(rowsFromRateItems(rates.data)));
    }
  }, [rates.data, reset]);

  const onSubmit = handleSubmit(async (values) => {
    setServerError(null);
    setSaved(false);
    const combos = emptyRateRows();
    const rows = combos.map((combo, index) => ({
      ...combo,
      rupees: values.rows[index]?.rupees ?? "",
    }));
    const items = rowsToRateItems(rows);
    if (items.length === 0) {
      setError("root", { message: "Set at least one rate before saving." });
      return;
    }
    try {
      await replaceRates.mutateAsync({ rates: items });
      setSaved(true);
    } catch (error) {
      setServerError(messageForError(error));
    }
  });

  if (shop.isPending || rates.isPending) {
    return (
      <p role="status" className="p-6 text-steel">
        Loading your rates…
      </p>
    );
  }

  if (shop.error instanceof ApiError && shop.error.code === "NOT_FOUND") {
    return (
      <section className="mx-auto flex w-full max-w-2xl flex-col gap-3 p-6">
        <h1 className="text-2xl font-semibold text-ink">Rates</h1>
        <p className="text-steel">
          This account does not have a shop yet. Register a shop to set rates.
        </p>
      </section>
    );
  }

  if (shop.isError || rates.isError) {
    const error = shop.error ?? rates.error;
    return (
      <section className="mx-auto flex w-full max-w-2xl flex-col gap-3 p-6">
        <h1 className="text-2xl font-semibold text-ink">Rates</h1>
        <Alert>{messageForError(error)}</Alert>
        <Button
          variant="secondary"
          onClick={() => {
            void shop.refetch();
            void rates.refetch();
          }}
        >
          Try again
        </Button>
      </section>
    );
  }

  return (
    <section className="mx-auto flex w-full max-w-2xl flex-col gap-6 p-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold text-ink">Rates</h1>
        <p className="text-steel">
          Prices per page for {shop.data.name}. Leave a row empty if the shop
          does not offer it.
        </p>
      </div>
      {!shop.data.is_verified && (
        <Alert variant="info">
          Your shop is not verified yet. Customers will see it after our team
          reviews it.
        </Alert>
      )}
      {saved && <Alert variant="success">Rates saved.</Alert>}
      {serverError !== null && <Alert>{serverError}</Alert>}
      {errors.root?.message !== undefined && (
        <Alert>{errors.root.message}</Alert>
      )}
      <form onSubmit={onSubmit} noValidate className="flex flex-col gap-3">
        <div className="overflow-x-auto rounded-md border border-hairline-soft bg-canvas">
          <table className="w-full border-collapse text-sm">
            <caption className="sr-only">Rates per page in rupees</caption>
            <thead>
              <tr className="border-b border-hairline-soft text-left text-steel">
                <th scope="col" className="px-3 py-2 font-medium">
                  Options
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Price per page (₹)
                </th>
              </tr>
            </thead>
            <tbody>
              {emptyRateRows().map((row, index) => {
                const label = rowLabel(row);
                const rowError = errors.rows?.[index]?.rupees?.message;
                return (
                  <tr
                    key={label}
                    className="border-b border-hairline-soft last:border-b-0"
                  >
                    <th
                      scope="row"
                      className="px-3 py-2 text-left font-normal text-ink"
                    >
                      {label}
                    </th>
                    <td className="px-3 py-2">
                      <Input
                        aria-label={`${label} price per page in rupees`}
                        inputMode="decimal"
                        className="max-w-28"
                        aria-invalid={rowError !== undefined}
                        {...register(`rows.${index}.rupees`)}
                      />
                      {rowError !== undefined && (
                        <p role="alert" className="mt-1 text-sm text-red-700">
                          {rowError}
                        </p>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div>
          <Button
            type="submit"
            pending={replaceRates.isPending}
            pendingLabel="Saving…"
          >
            Save rates
          </Button>
        </div>
      </form>
    </section>
  );
}
