import { expect, test } from "@playwright/test";

import { signInAsCustomer } from "./helpers";

// The customer is warned about a file that will not print well.
//
// The file is a picture of a business card stretched across a page, so
// the effective resolution is about 29 dots per inch. The report says so,
// the customer acknowledges it, and the order goes through anyway: the
// check is advice, not a gate.
//
// It runs against the local stack, where the worker does the analysis
// and the fake payment gateway takes the money.
//
// The worker measures the file in the background, and it looks at the
// queue every thirty seconds, so the report can take a minute to
// arrive. The test's own limit is longer than that, because the wait
// is the worker's and not the browser's.

test.setTimeout(120_000);

const SHOP_NAME = "Central Prints";

test("a customer is warned about a low resolution file and still orders", async ({
  browser,
}) => {
  const customerContext = await browser.newContext();
  const customer = await customerContext.newPage();
  await signInAsCustomer(customer);

  // The customer uploads the file.
  await customer.goto("/new");
  await customer
    .locator('input[type="file"]')
    .setInputFiles("tests/fixtures/low-resolution.pdf");
  await expect(customer.getByText("Paper size")).toBeVisible({
    timeout: 30_000,
  });

  await customer.getByRole("radio", { name: "A4" }).check();
  await customer.getByLabel("Copies").fill("1");
  await customer.getByRole("button", { name: "Continue" }).click();

  const shop = customer.locator("li").filter({ hasText: SHOP_NAME }).first();
  await expect(shop).toBeVisible();
  await shop.getByRole("button", { name: "Choose this shop" }).click();
  await customer.getByRole("button", { name: "Continue to payment" }).click();

  // The warning appears once the worker has measured the file. The
  // worker runs every thirty seconds, so this waits for two of its
  // rounds rather than guessing at a time.
  const warning = customer.getByRole("region", { name: "File quality" });
  await expect(
    warning.getByRole("heading", { name: /check your file quality/i }),
  ).toBeVisible({ timeout: 120_000 });
  await expect(warning.getByText(/page 1/i)).toBeVisible();
  await expect(warning.getByText(/too few pixels/i)).toBeVisible();

  // The customer acknowledges it, and the checkout is still there.
  await warning.getByRole("button", { name: /acknowledge/i }).click();
  await expect(warning.getByText(/warnings acknowledged/i)).toBeVisible({
    timeout: 20_000,
  });

  // The order goes through. The warning did not stop it.
  await customer.getByRole("button", { name: /^Pay /i }).click();
  await expect(customer.getByText("Payment received")).toBeVisible({
    timeout: 30_000,
  });
});
