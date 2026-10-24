import { expect, test, type Page } from "@playwright/test";

import { signIn as signInHelper, signInAsCustomer } from "./helpers";

// The whole product, in a browser, with two people.
//
// The customer uploads a file, gets a price, pays and is shown a pickup
// code. The shop, in a second browser, works the order from the queue to
// the handover. The customer sees the order collected.
//
// It runs against the local stack with the fake payment gateway, so no
// money moves and no real payment provider is involved.

const SHOP_NAME = "Central Prints";
const VENDOR_EMAIL = "vendor1@example.com";

test("a customer pays and a shop hands the order over", async ({ browser }) => {
  const customerContext = await browser.newContext();
  const customer = await customerContext.newPage();
  await signInAsCustomer(customer);

  // The customer uploads the file.
  await customer.goto("/new");
  await customer
    .locator('input[type="file"]')
    .setInputFiles("tests/fixtures/one-page.pdf");

  // The wizard moves on to the options as soon as the file is stored, so
  // wait for that step rather than clicking through it.
  await expect(customer.getByText("Paper size")).toBeVisible({
    timeout: 20_000,
  });

  // The customer chooses the options.
  await customer.getByRole("radio", { name: "A4" }).check();
  await customer.getByLabel("Print in colour").check();
  await customer.getByLabel("Copies").fill("2");
  await customer.getByRole("button", { name: "Continue" }).click();

  // The customer picks the shop. The shop is picked by name so the test
  // does not depend on the order the list happens to come back in.
  const shop = customer.locator("li").filter({ hasText: SHOP_NAME }).first();
  await expect(shop).toBeVisible();
  await shop.getByRole("button", { name: "Choose this shop" }).click();
  await customer.getByRole("button", { name: "Continue to payment" }).click();

  // The customer pays. The local stack uses the fake gateway, so the
  // payment is confirmed immediately.
  await customer.getByRole("button", { name: /pay/i }).click();
  await expect(customer.getByText("Payment received")).toBeVisible({
    timeout: 30_000,
  });
  const pickupCode = (
    await customer
      .locator("p.font-mono")
      .filter({ hasText: /^[0-9]{6}$/ })
      .first()
      .textContent()
  )?.trim();
  expect(pickupCode).toMatch(/^[0-9]{6}$/);

  // The order number, so the shop can find this order and not somebody
  // else's that happens to be in the queue.
  const orderNumber = (
    await customer.getByText(/Order #\d+ is paid/).textContent()
  ).match(/#(\d+)/)?.[1];
  expect(orderNumber).toBeTruthy();

  // The estimate belongs to the shop, not a promised start time for this order.
  await customer.getByRole("link", { name: "View order" }).click();
  await expect(
    customer.getByRole("region", { name: "Current queue wait at this shop" }),
  ).toBeVisible();
  await expect(
    customer.getByText(/new order, until printing starts/),
  ).toBeVisible();
  const orderUrl = customer.url();

  // The shop works the order. A second browser, a different person.
  const vendorContext = await browser.newContext();
  const vendor = await vendorContext.newPage();
  await signInHelper(vendor, VENDOR_EMAIL);
  await vendor.goto("/vendor");

  // The board has one card per active order, and the card moves between
  // the four columns as the shop works it. The board polls every five
  // seconds, so each move takes a moment to show up.
  const card = (name: string) =>
    vendor
      .getByRole("region", { name })
      .getByRole("article")
      .filter({ hasText: `#${orderNumber}` });

  await expect(card("New")).toBeVisible({ timeout: 15_000 });
  await card("New").getByRole("button", { name: "Accept" }).click();
  await expect(card("Accepted")).toBeVisible({ timeout: 15_000 });

  await card("Accepted")
    .getByRole("button", { name: "Start printing" })
    .click();
  await expect(card("Printing")).toBeVisible({ timeout: 15_000 });

  await card("Printing").getByRole("button", { name: "Mark ready" }).click();
  await expect(card("Ready")).toBeVisible({ timeout: 15_000 });

  // A wrong code is refused.
  await card("Ready").getByRole("button", { name: "Verify pickup" }).click();
  await vendor.getByLabel("Pickup code").fill("000000");
  await vendor.getByRole("button", { name: "Hand over" }).click();
  await expect(vendor.getByRole("alert")).toContainText(/code does not match/i);

  // The right code completes the order.
  await vendor.getByLabel("Pickup code").fill(pickupCode as string);
  await vendor.getByRole("button", { name: "Hand over" }).click();
  // A collected order is no longer active, so it leaves the board.
  await expect(card("Ready")).toHaveCount(0, { timeout: 15_000 });

  // The customer sees the finished order on the order page.
  await customer.goto(orderUrl);
  await expect(customer).toHaveURL(/\/orders\//);
  await expect(customer.getByText("Collected").first()).toBeVisible({
    timeout: 20_000,
  });
  // The pickup code is still shown, because it is the customer's proof.
  await expect(
    customer
      .getByLabel("Pickup code")
      .locator("p")
      .filter({ hasText: pickupCode as string }),
  ).toBeVisible();

  await vendorContext.close();
  await customerContext.close();
});
