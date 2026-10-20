import { expect, type Page } from "@playwright/test";

// The customer every journey test uses.
//
// Registration is rate limited per address, and every test in this
// suite comes from the same one. Creating a customer per test would
// trip that limit and make the suite flaky, so one customer is created
// once, before the tests start, and shared.

export const CUSTOMER_EMAIL = "e2e-customer@example.com";
export const CUSTOMER_PASSWORD = "e2e-password-123";
export const SEEDED_PASSWORD = "spn-demo-password";

// The API the tests call directly.
//
// The browser goes through the frontend, so most of the suite never
// needs this. The tests that read something the browser does not show
// do, and the port is configurable because another program on the
// machine may already have it.
export const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000";

export async function signIn(
  page: Page,
  email: string,
  password: string,
): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login$/);
}

/** Sign in as the shared customer. */
export function signInAsCustomer(page: Page): Promise<void> {
  return signIn(page, CUSTOMER_EMAIL, CUSTOMER_PASSWORD);
}
