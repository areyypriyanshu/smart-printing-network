import { z } from "zod";

export const PAPER_SIZES = ["A4", "A3"] as const;

export const optionsSchema = z.object({
  paper_size: z.enum(PAPER_SIZES),
  color: z.boolean(),
  duplex: z.boolean(),
  copies: z.coerce
    .number("Enter a whole number of copies")
    .int("Enter a whole number of copies")
    .min(1, "At least 1 copy")
    .max(100, "At most 100 copies"),
});

export type OptionsFormValues = z.infer<typeof optionsSchema>;
export type OptionsFormInput = z.input<typeof optionsSchema>;

export const OPTION_DEFAULTS: OptionsFormValues = {
  paper_size: "A4",
  color: false,
  duplex: false,
  copies: 1,
};

export function describeOptions(options: OptionsFormValues): string {
  const parts = [
    options.paper_size,
    options.color ? "colour" : "black and white",
    options.duplex ? "double-sided" : "single-sided",
    options.copies === 1 ? "1 copy" : `${options.copies} copies`,
  ];
  return parts.join(" · ");
}
