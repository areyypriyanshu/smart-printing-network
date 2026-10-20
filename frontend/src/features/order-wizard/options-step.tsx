import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { Button, Input } from "../../components/ui";
import {
  PAPER_SIZES,
  optionsSchema,
  type OptionsFormInput,
  type OptionsFormValues,
} from "./schemas";

type OptionsStepProps = {
  defaultValues: OptionsFormValues;
  onBack: () => void;
  onContinue: (options: OptionsFormValues) => void;
};

export function OptionsStep({
  defaultValues,
  onBack,
  onContinue,
}: OptionsStepProps) {
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<OptionsFormInput, unknown, OptionsFormValues>({
    resolver: zodResolver(optionsSchema),
    defaultValues,
  });

  const onSubmit = handleSubmit((values) => onContinue(values));

  return (
    <form
      onSubmit={onSubmit}
      noValidate
      className="flex flex-col gap-6 rounded-lg border border-beige-deep bg-cream p-6"
    >
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

      <div className="flex gap-3">
        <Button type="button" variant="secondary" onClick={onBack}>
          Back
        </Button>
        <Button type="submit">Continue</Button>
      </div>
    </form>
  );
}
