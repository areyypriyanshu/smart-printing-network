import type { FieldErrors, UseFormRegister } from "react-hook-form";

import { Input } from "../../components/ui";
import { PAPER_SIZES, type OptionsFormInput } from "./schemas";

export type OptionsFieldsProps = {
  register: UseFormRegister<OptionsFormInput>;
  errors: FieldErrors<OptionsFormInput>;
};

/**
 * The print options: the paper, the colour, the sides and the copies.
 *
 * They are here on their own because two screens need them. The order
 * wizard asks for them as a step, and the shop search asks for them so
 * that it can show what each shop would charge. One set of fields and
 * one set of rules, so the two screens cannot drift apart.
 */
export function OptionsFields({ register, errors }: OptionsFieldsProps) {
  return (
    <>
      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium text-ink">Paper size</legend>
        <div className="flex gap-3">
          {PAPER_SIZES.map((size) => (
            <label
              key={size}
              className="flex min-h-11 cursor-pointer items-center gap-2 rounded-md border border-hairline-strong bg-canvas px-4 py-2 text-sm text-ink has-checked:border-primary has-checked:bg-cream-deeper"
            >
              <input
                type="radio"
                value={size}
                className="accent-primary"
                {...register("paper_size")}
              />
              {size}
            </label>
          ))}
        </div>
      </fieldset>

      <div className="flex flex-col gap-2">
        <label className="flex min-h-11 items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            className="accent-primary"
            {...register("color")}
          />
          Print in colour
        </label>
        <label className="flex min-h-11 items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            className="accent-primary"
            {...register("duplex")}
          />
          Print on both sides
        </label>
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="copies" className="text-sm font-medium text-ink">
          Copies
        </label>
        <Input
          id="copies"
          type="number"
          min={1}
          max={100}
          inputMode="numeric"
          className="max-w-32"
          aria-invalid={errors.copies !== undefined}
          aria-describedby={
            errors.copies !== undefined ? "copies-error" : undefined
          }
          {...register("copies")}
        />
        {errors.copies?.message !== undefined && (
          <p id="copies-error" role="alert" className="text-sm text-danger">
            {errors.copies.message}
          </p>
        )}
      </div>
    </>
  );
}
