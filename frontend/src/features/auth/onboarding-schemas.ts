import { z } from "zod";

/**
 * What a person says they are here for.
 *
 * The address and the name are not asked for. The identity provider
 * holds them, and it proved them, and the account carries the ones the
 * provider has rather than the ones a form offered.
 */
export const onboardingSchema = z
  .object({
    role: z.enum(["customer", "vendor"]),
    shop_name: z.string().trim().max(200, "Too long"),
    shop_address: z.string().trim().max(500, "Too long"),
    phone: z
      .string()
      .trim()
      .refine(
        (value) =>
          value === "" ||
          (/^[0-9+() .-]{7,25}$/.test(value) &&
            value.replace(/[^0-9]/g, "").length >= 7 &&
            value.replace(/[^0-9]/g, "").length <= 15),
        "Enter a phone number with 7 to 15 digits",
      )
      .optional(),
    latitude: z.string().trim(),
    longitude: z.string().trim(),
  })
  .superRefine((values, context) => {
    if (values.role !== "vendor") return;
    if (values.shop_name.length === 0) {
      context.addIssue({
        code: "custom",
        path: ["shop_name"],
        message: "Enter the shop name",
      });
    }
    if (values.shop_address.length === 0) {
      context.addIssue({
        code: "custom",
        path: ["shop_address"],
        message: "Enter the shop address",
      });
    }
    const latitude = Number(values.latitude);
    if (!Number.isFinite(latitude) || latitude < -90 || latitude > 90) {
      context.addIssue({
        code: "custom",
        path: ["latitude"],
        message: "Enter a latitude between -90 and 90",
      });
    }
    const longitude = Number(values.longitude);
    if (!Number.isFinite(longitude) || longitude < -180 || longitude > 180) {
      context.addIssue({
        code: "custom",
        path: ["longitude"],
        message: "Enter a longitude between -180 and 180",
      });
    }
  });

export type OnboardingValues = z.infer<typeof onboardingSchema>;
