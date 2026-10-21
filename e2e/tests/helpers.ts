import { expect, type Page } from "@playwright/test";

// The customer every journey test uses.
//
// The account is created once, before the tests start, and shared. The
// end to end suite signs in through the local way in, which is the one
// the application offers when the identity provider is not in the
// picture, and the local way in makes the account if it is not there.

export const CUSTOMER_EMAIL = "e2e-customer@example.com";

// The API the tests call directly.
//
// The browser goes through the frontend, so most of the suite never
// needs this. The tests that read something the browser does not show
// do, and the port is configurable because another program on the
// machine may already have it.
export const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000";

export async function signIn(page: Page, email: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login$/);
}

/** Sign in as the shared customer. */
export function signInAsCustomer(page: Page): Promise<void> {
  return signIn(page, CUSTOMER_EMAIL);
}
