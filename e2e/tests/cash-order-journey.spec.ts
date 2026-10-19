import { expect, test, type Page } from "@playwright/test";

// The same product, paid in cash.
//
// The customer reserves the job, shows the code at the counter and pays
// there. The shop takes the money when it hands the printout over.
//
// It runs against the local stack with the fake payment gateway, so no
// money moves and no real payment provider is involved.

const SHOP_NAME = "Central Prints";
const VENDOR_EMAIL = "vendor1@example.com";
const PASSWORD = "spn-demo-password";

async function registerCustomer(page: Page, email: string) {
  await page.goto("/register");
  await page.getByLabel("Full name").fill("Cash Customer");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill("e2e-password-123");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/login$/);
}

async function signIn(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).not.toHaveURL(/\/login$/);
}

test("a customer reserves a job and pays for it at the counter", async ({
  browser,
}) => {
  const customerContext = await browser.newContext();
  const customer = await customerContext.newPage();
  const email = `e2e-cash-${Date.now()}@example.com`;

  await registerCustomer(customer, email);
  await signIn(customer, email, "e2e-password-123");

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
  await signIn(vendor, VENDOR_EMAIL, PASSWORD);
  await vendor.goto("/vendor");

  const newColumn = vendor.getByRole("region", { name: "New" });
  await expect(newColumn.getByText("Pay at shop").first()).toBeVisible({
    timeout: 15_000,
  });

  // The shop works the order as it would any other.
  const card = newColumn.getByRole("article").first();
  await card.getByRole("button", { name: "Accept" }).click();
  await expect(
    vendor
      .getByRole("region", { name: "Accepted" })
      .getByRole("article")
      .first(),
  ).toBeVisible({ timeout: 15_000 });
  await vendor.getByRole("button", { name: "Start printing" }).click();
  await expect(
    vendor
      .getByRole("region", { name: "Printing" })
      .getByRole("article")
      .first(),
  ).toBeVisible({ timeout: 15_000 });
  await vendor.getByRole("button", { name: "Mark ready" }).click();
  await expect(
    vendor.getByRole("region", { name: "Ready" }).getByRole("article").first(),
  ).toBeVisible({ timeout: 15_000 });

  // The shop is told how much to take, and the wrong code is refused.
  await vendor.getByRole("button", { name: "Verify pickup" }).click();
  await expect(vendor.getByText(/Take ₹/)).toBeVisible();
  await vendor.getByLabel("Pickup code").fill("000000");
  await vendor.getByRole("button", { name: "Hand over" }).click();
  await expect(vendor.getByRole("alert")).toContainText(/code does not match/i);

  // The right code hands the printout over, and takes the money.
  await vendor.getByLabel("Pickup code").fill(pickupCode as string);
  await vendor.getByRole("button", { name: "Hand over" }).click();
  await expect(
    vendor.getByRole("region", { name: "Ready" }).getByRole("article"),
  ).toHaveCount(0, { timeout: 15_000 });

  // The customer sees it collected and paid in cash.
  await customer.getByRole("link", { name: "View order" }).click();
  await expect(customer).toHaveURL(/\/orders\//);
  await expect(customer.getByText(/Collected and paid in cash/i)).toBeVisible({
    timeout: 20_000,
  });

  await vendorContext.close();
  await customerContext.close();
});
