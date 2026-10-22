import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { Button } from "../../components/ui";
import { OptionsFields } from "./options-fields";
import {
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
      <OptionsFields register={register} errors={errors} />

      <div className="flex gap-3">
        <Button type="button" variant="secondary" onClick={onBack}>
          Back
        </Button>
        <Button type="submit">Continue</Button>
      </div>
    </form>
  );
}
