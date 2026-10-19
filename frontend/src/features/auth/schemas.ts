import { z } from "zod";

export const loginSchema = z.object({
  email: z.email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password"),
});

export type LoginValues = z.infer<typeof loginSchema>;

export const registerSchema = z.object({
  email: z.email("Enter a valid email address"),
  full_name: z.string().trim().min(1, "Enter your name").max(200, "Too long"),
  password: z
    .string()
    .min(8, "Use at least 8 characters")
    .max(128, "Use 128 characters or fewer"),
});

export type RegisterValues = z.infer<typeof registerSchema>;

const coordinate = (min: number, max: number, label: string) =>
  z
    .string()
    .trim()
    .min(1, `Enter the ${label}`)
    .refine(
      (value) =>
        Number.isFinite(Number(value)) &&
        Number(value) >= min &&
        Number(value) <= max,
      `Enter a ${label} between ${min} and ${max}`,
    );

export const registerVendorSchema = registerSchema.extend({
  shop_name: z
    .string()
    .trim()
    .min(1, "Enter the shop name")
    .max(200, "Too long"),
  shop_address: z
    .string()
    .trim()
    .min(1, "Enter the shop address")
    .max(500, "Too long"),
  latitude: coordinate(-90, 90, "latitude"),
  longitude: coordinate(-180, 180, "longitude"),
});

export type RegisterVendorValues = z.infer<typeof registerVendorSchema>;
