import { describe, expect, it } from "vitest";

import { loginSchema, registerSchema, registerVendorSchema } from "./schemas";

describe("loginSchema", () => {
  it("accepts a valid email and any non-empty password", () => {
    expect(
      loginSchema.safeParse({ email: "a@b.com", password: "x" }).success,
    ).toBe(true);
  });

  it("rejects a malformed email", () => {
    expect(
      loginSchema.safeParse({ email: "not-an-email", password: "x" }).success,
    ).toBe(false);
  });

  it("rejects an empty password", () => {
    expect(
      loginSchema.safeParse({ email: "a@b.com", password: "" }).success,
    ).toBe(false);
  });
});

describe("registerSchema", () => {
  it("requires at least 8 characters in the password", () => {
    const base = { email: "a@b.com", full_name: "A B" };
    expect(
      registerSchema.safeParse({ ...base, password: "1234567" }).success,
    ).toBe(false);
    expect(
      registerSchema.safeParse({ ...base, password: "12345678" }).success,
    ).toBe(true);
  });
});

describe("registerVendorSchema", () => {
  const valid = {
    email: "shop@example.com",
    full_name: "Shop Owner",
    password: "password-123",
    shop_name: "Shop",
    shop_address: "1 Main Road",
    phone: "",
    latitude: "22.5726",
    longitude: "88.3639",
  };

  it("accepts valid Kolkata coordinates", () => {
    expect(registerVendorSchema.safeParse(valid).success).toBe(true);
  });

  it("rejects out-of-range coordinates", () => {
    expect(
      registerVendorSchema.safeParse({ ...valid, latitude: "95" }).success,
    ).toBe(false);
    expect(
      registerVendorSchema.safeParse({ ...valid, longitude: "-181" }).success,
    ).toBe(false);
  });

  it("rejects non-numeric coordinates", () => {
    expect(
      registerVendorSchema.safeParse({ ...valid, latitude: "north" }).success,
    ).toBe(false);
  });

  it("accepts a phone number", () => {
    expect(
      registerVendorSchema.safeParse({ ...valid, phone: "+91 98300 00000" })
        .success,
    ).toBe(true);
  });

  it("rejects a phone number that is not one", () => {
    expect(
      registerVendorSchema.safeParse({ ...valid, phone: "call me" }).success,
    ).toBe(false);
    expect(
      registerVendorSchema.safeParse({ ...valid, phone: "12345" }).success,
    ).toBe(false);
  });
});
