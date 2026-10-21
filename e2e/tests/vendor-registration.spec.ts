import { expect, test } from "@playwright/test";

import { API_URL } from "./helpers";

/**
 * A shop owner.
 *
 * The role is chosen once and never changes in the product, so the
 * suite asks for the account it wants rather than making an account
 * and then changing it. The shop is made with it, and the shop waits
 * for the team to look at it, which is the same rule as it has always
 * been.
 */
test("a shop owner has a shop waiting for the team to look at it", async ({
  page,
  request,
}) => {
  const email = `vendor-e2e-${Date.now()}@example.com`;

  const made = await request.post(`${API_URL}/api/v1/auth/dev-session`, {
    data: {
      email,
      full_name: "E2E Vendor",
      role: "vendor",
      shop_name: "Kharghar E2E Print",
      shop_address: "Sector 12, Kharghar, Navi Mumbai",
      latitude: 19.0473,
      longitude: 73.0699,
    },
  });
  expect(made.status()).toBe(200);

  // The owner signs in and lands on the page a shop owner lands on.
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login$/);

  await page.goto("/vendor");
  await expect(page.getByRole("heading", { name: /queue|orders/i })).toBeVisible();
});
