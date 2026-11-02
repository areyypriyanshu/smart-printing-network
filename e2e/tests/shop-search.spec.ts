import { expect, test } from "@playwright/test";

import { signInAsCustomer } from "./helpers";

/**
 * A customer who looks for a shop near them.
 *
 * The browser is allowed to share a location, and it is given one that
 * is in Kolkata, where the seeded shops are. The customer then chooses
 * a file, so the page can say what each shop would charge, and carries
 * the file and the shop into the order.
 */
test.use({
  geolocation: { latitude: 22.5726, longitude: 88.3639 },
  permissions: ["geolocation"],
});

test("a customer finds the shops near them and compares their prices", async ({
  page,
}) => {
  await signInAsCustomer(page);
  await page.goto("/shops");

  await page.getByRole("button", { name: /find shops near me/i }).click();

  // The shops are found by their distance from the customer, and each
  // one says how far away it is.
  const shop = page.locator("li").filter({ hasText: "Central Prints" }).first();
  await expect(shop).toBeVisible({ timeout: 20_000 });
  await expect(shop.getByText(/away$/)).toBeVisible();

  // A file, and the prices that go with it.
  await page
    .locator('input[type="file"]')
    .setInputFiles("tests/fixtures/one-page.pdf");
  await expect(page.getByText(/one-page\.pdf/)).toBeVisible({
    timeout: 20_000,
  });
  await expect(shop.getByText(/per page/)).toBeVisible();
  await expect(shop.getByText(/Current queue wait:/)).toBeVisible();
  await expect(
    shop.getByText(/new order, until printing starts/),
  ).toBeVisible();

  // The customer picks a shop, and the file and the options come with
  // them into the order.
  await shop.getByRole("button", { name: /order from this shop/i }).click();
  await expect(page).toHaveURL(/\/new/);
  await expect(page.getByText("Paper size")).toBeVisible({
    timeout: 20_000,
  });
});

test.describe("the order wizard with a distant customer", () => {
  test.use({
    geolocation: { latitude: 23.7957, longitude: 86.4304 },
    permissions: ["geolocation"],
  });

  test("keeps shops that are farther than five kilometres", async ({
    page,
  }) => {
    await signInAsCustomer(page);
    await page.goto("/new");
    await page
      .locator('input[type="file"]')
      .setInputFiles("tests/fixtures/one-page.pdf");

    await expect(page.getByText("Paper size")).toBeVisible({ timeout: 20_000 });
    await page.getByRole("button", { name: "Continue" }).click();
    await page.getByRole("button", { name: /find shops near me/i }).click();

    const shop = page
      .locator("li")
      .filter({ hasText: "Central Prints" })
      .first();
    await expect(shop).toBeVisible({ timeout: 20_000 });
    await expect(shop.getByText(/km away/)).toBeVisible();
    await expect(page.getByText(/no verified shops yet/i)).toHaveCount(0);
  });
});
