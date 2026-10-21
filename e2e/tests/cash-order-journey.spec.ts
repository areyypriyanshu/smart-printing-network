import { expect, test, type Page } from "@playwright/test";

import {
  signIn as signInHelper,
  signInAsCustomer,
} from "./helpers";

// The same product, paid in cash.
//
// The customer reserves the job, shows the code at the counter and pays
// there. The shop takes the money when it hands the printout over.
//
// It runs against the local stack with the fake payment gateway, so no
// money moves and no real payment provider is involved.

const SHOP_NAME = "Central Prints";
const VENDOR_EMAIL = "vendor1@example.com";

test("a customer reserves a job and pays for it at the counter", async ({
  browser,
}) => {
  const customerContext = await browser.newContext();
  const customer = await customerContext.newPage();
  await signInAsCustomer(customer);

  // The customer uploads the file and picks the options.
  await customer.goto("/new");
  await customer
    .locator('input[type="file"]')
    .setInputFiles("tests/fixtures/one-page.pdf");
  await expect(customer.getByText("Paper size")).toBeVisible({
    timeout: 20_000,
  });
  await customer.getByRole("radio", { name: "A4" }).check();
  await customer.getByLabel("Copies").fill("1");
  await customer.getByRole("button", { name: "Continue" }).click();

  // The customer picks the shop, by name, so the test does not depend on
  // the order the list comes back in.
  const shop = customer.locator("li").filter({ hasText: SHOP_NAME }).first();
  await expect(shop).toBeVisible();
  await shop.getByRole("button", { name: "Choose this shop" }).click();
  await customer.getByRole("button", { name: "Continue to payment" }).click();

  // The customer chooses to pay at the shop.
  await customer.getByRole("radio", { name: /pay at the shop/i }).check();
  await customer.getByRole("button", { name: /reserve for/i }).click();

  // The code is there straight away. There is no provider to wait for.
  await expect(customer.getByText("Reserved for you")).toBeVisible({
    timeout: 30_000,
  });
  const orderNumber = (
    await customer.getByText(/Order #\d+ is booked/).textContent()
  ).match(/#(\d+)/)?.[1];
  expect(orderNumber).toBeTruthy();
  const pickupCode = (
    await customer
      .locator("p.font-mono")
      .filter({ hasText: /^[0-9]{6}$/ })
      .first()
      .textContent()
  )?.trim();
  expect(pickupCode).toMatch(/^[0-9]{6}$/);

  // The shop sees it in the queue, marked as one to pay for in cash.
  const vendorContext = await browser.newContext();
  const vendor = await vendorContext.newPage();
  await signInHelper(vendor, VENDOR_EMAIL);
  await vendor.goto("/vendor");

  const newColumn = vendor.getByRole("region", { name: "New" });
  await expect(newColumn.getByText("Pay at shop").first()).toBeVisible({
    timeout: 15_000,
  });

  // The shop works the order as it would any other. The card is found
  // by the pickup code, so another order in the queue does not get in
  // the way.
  const thisOrder = (region: string) =>
    vendor
      .getByRole("region", { name: region })
      .getByRole("article")
      .filter({ hasText: `#${orderNumber}` });
  const card = newColumn
    .getByRole("article")
    .filter({ hasText: `#${orderNumber}` });
  await card.getByRole("button", { name: "Accept" }).click();
  await expect(thisOrder("Accepted")).toBeVisible({ timeout: 15_000 });
  await thisOrder("Accepted")
    .getByRole("button", { name: "Start printing" })
    .click();
  await expect(thisOrder("Printing")).toBeVisible({ timeout: 15_000 });
  await thisOrder("Printing")
    .getByRole("button", { name: "Mark ready" })
    .click();
  await expect(thisOrder("Ready")).toBeVisible({ timeout: 15_000 });

  // The shop is told how much to take, and the wrong code is refused.
  await thisOrder("Ready")
    .getByRole("button", { name: "Verify pickup" })
    .click();
  await expect(vendor.getByText(/Take ₹/)).toBeVisible();
  await vendor.getByLabel("Pickup code").fill("000000");
  await vendor.getByRole("button", { name: "Hand over" }).click();
  await expect(vendor.getByRole("alert")).toContainText(/code does not match/i);

  // The right code hands the printout over, and takes the money.
  await vendor.getByLabel("Pickup code").fill(pickupCode as string);
  await vendor.getByRole("button", { name: "Hand over" }).click();
  await expect(thisOrder("Ready")).toHaveCount(0, { timeout: 15_000 });

  // The customer sees it collected and paid in cash.
  await customer.getByRole("link", { name: "View order" }).click();
  await expect(customer).toHaveURL(/\/orders\//);
  await expect(customer.getByText(/Collected and paid in cash/i)).toBeVisible({
    timeout: 20_000,
  });

  await vendorContext.close();
  await customerContext.close();
});
