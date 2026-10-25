// Captures the README screenshots from a running stack.
//
// The screenshots are not mockups: every one is a real page from the
// local stack, driven the way a person drives it, with the seeded shops
// and the fake payment gateway. The customer account is created by the
// local way in. That is the point of putting them in the README: a
// reader can reproduce them with the commands below.
//
//   make up && make migrate && make seed
//   SPN_DEV_AUTH=true VITE_SPN_DEV_AUTH=true docker compose up -d api frontend
//   cd e2e && npm ci && npx playwright install chrome
//   node capture-screenshots.mjs
//
// The images land in docs/screenshots/. A screen that fails is reported
// and the script exits nonzero. Some steps are shared by several
// screens, so an early failure can stop the run rather than skipping
// only the affected image.

import { mkdir } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "..");
const OUT = resolve(REPO, "docs/screenshots");
const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:5173";

// The capture creates accounts and orders, so it only drives a local
// stack unless the operator says otherwise.
if (
  !["localhost", "127.0.0.1", "[::1]"].includes(new URL(BASE_URL).hostname) &&
  process.env.E2E_ALLOW_REMOTE !== "1"
) {
  throw new Error(
    `refusing to drive ${BASE_URL}: the capture creates accounts and orders. Set E2E_ALLOW_REMOTE=1 to allow a non-local host.`,
  );
}

const CUSTOMER_EMAIL = "e2e-customer@example.com";
const VENDOR_EMAIL = "vendor1@example.com";
const SHOP_NAME = "Central Prints";

const DESKTOP = { width: 1440, height: 900 };
const PHONE = { width: 390, height: 844 };
const KOLKATA = { latitude: 22.5726, longitude: 88.3639 };

const done = [];
const failed = [];

async function shot(page, name) {
  await page.screenshot({ path: resolve(OUT, `${name}.png`), fullPage: false });
  done.push(name);
}

async function signIn(page, email) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.endsWith("/login"), { timeout: 30_000 });
}

/** Run one screen, and report rather than throw if it could not be taken. */
async function screen(name, fn) {
  try {
    await fn();
    console.log(`  ok      ${name}`);
  } catch (error) {
    failed.push(`${name}: ${error.message.split("\n")[0]}`);
    console.log(`  FAILED  ${name}: ${error.message.split("\n")[0]}`);
  }
}

async function main() {
  await mkdir(OUT, { recursive: true });
  const browser = await chromium.launch({ channel: "chrome" });

  // --- the anonymous visitor -------------------------------------------
  const anon = await browser.newContext({ viewport: DESKTOP, baseURL: BASE_URL });
  const anonPage = await anon.newPage();
  await screen("01-landing", async () => {
    await anonPage.goto("/");
    await anonPage.waitForLoadState("networkidle");
    await shot(anonPage, "01-landing");
  });
  await screen("02-sign-in", async () => {
    await anonPage.goto("/login");
    await anonPage.getByLabel("Email").waitFor({ timeout: 20_000 });
    await shot(anonPage, "02-sign-in");
  });
  await anon.close();

  // --- the customer -----------------------------------------------------
  const customerContext = await browser.newContext({
    viewport: DESKTOP,
    baseURL: BASE_URL,
    geolocation: KOLKATA,
    permissions: ["geolocation"],
  });
  const customer = await customerContext.newPage();
  await signIn(customer, CUSTOMER_EMAIL);

  await customer.goto("/shops");
  await screen("03-compare-shops", async () => {
    await customer.getByRole("button", { name: /find shops near me/i }).click();
    await customer
      .locator("li")
      .filter({ hasText: SHOP_NAME })
      .first()
      .waitFor({ timeout: 30_000 });
    await customer
      .locator('input[type="file"]')
      .setInputFiles("tests/fixtures/one-page.pdf");
    await customer.getByText(/one-page\.pdf/).waitFor({ timeout: 30_000 });
    await customer.getByText(/Current queue wait:/).first().waitFor({ timeout: 30_000 });
    await customer
      .locator("li")
      .filter({ hasText: SHOP_NAME })
      .first()
      .scrollIntoViewIfNeeded();
    await shot(customer, "03-compare-shops");
  });

  // Carry the chosen shop and file into the order, so the next screens are
  // one continuous journey rather than unrelated pages.
  await customer
    .locator("li")
    .filter({ hasText: SHOP_NAME })
    .first()
    .getByRole("button", { name: /order from this shop/i })
    .click();
  await customer.getByText("Paper size").waitFor({ timeout: 30_000 });

  await screen("04-print-options", async () => {
    await customer.getByRole("radio", { name: "A4" }).check();
    await customer.getByLabel("Print in colour").check();
    await customer.getByLabel("Copies").fill("2");
    await shot(customer, "04-print-options");
  });

  await customer.getByRole("button", { name: "Continue" }).click();
  await customer
    .locator("li")
    .filter({ hasText: SHOP_NAME })
    .first()
    .getByRole("button", { name: "Choose this shop" })
    .click();

  await screen("05-payment", async () => {
    await customer.getByRole("button", { name: "Continue to payment" }).click();
    await customer.getByRole("button", { name: /^Pay /i }).waitFor({ timeout: 30_000 });
    await shot(customer, "05-payment");
  });

  let orderUrl = null;
  await screen("06-payment-received", async () => {
    await customer.getByRole("button", { name: /^Pay /i }).click();
    await customer.getByText("Payment received").waitFor({ timeout: 45_000 });
    await shot(customer, "06-payment-received");
    await customer.getByRole("link", { name: "View order" }).click();
    await customer.waitForURL(/\/orders\//, { timeout: 30_000 });
    orderUrl = customer.url();
  });

  await screen("07-order-and-pickup-code", async () => {
    if (orderUrl) await customer.goto(orderUrl);
    await customer
      .getByRole("region", { name: "Current queue wait at this shop" })
      .waitFor({ timeout: 30_000 });
    await shot(customer, "07-order-and-pickup-code");
  });

  // --- the same order at phone width ------------------------------------
  const phoneContext = await browser.newContext({
    viewport: PHONE,
    baseURL: BASE_URL,
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
  });
  const phone = await phoneContext.newPage();
  await signIn(phone, CUSTOMER_EMAIL);
  await screen("08-order-phone", async () => {
    if (!orderUrl) throw new Error("no order to open");
    await phone.goto(orderUrl);
    await phone.getByText(/Pickup code/i).first().waitFor({ timeout: 30_000 });
    await shot(phone, "08-order-phone");
  });
  await phoneContext.close();

  // --- the shop counter --------------------------------------------------
  const vendorContext = await browser.newContext({ viewport: DESKTOP, baseURL: BASE_URL });
  const vendor = await vendorContext.newPage();
  await signIn(vendor, VENDOR_EMAIL);
  await screen("09-vendor-queue", async () => {
    await vendor.goto("/vendor");
    await vendor
      .getByRole("region", { name: "New" })
      .getByRole("article")
      .first()
      .waitFor({ timeout: 30_000 });
    await shot(vendor, "09-vendor-queue");
  });

  await vendorContext.close();
  await customerContext.close();

  // --- the quality check, which is measured by the worker ----------------
  const qualityContext = await browser.newContext({ viewport: DESKTOP, baseURL: BASE_URL });
  const quality = await qualityContext.newPage();
  await signIn(quality, CUSTOMER_EMAIL);
  await screen("10-quality-warning", async () => {
    quality.setDefaultTimeout(150_000);
    await quality.goto("/new");
    await quality
      .locator('input[type="file"]')
      .setInputFiles("tests/fixtures/low-resolution.pdf");
    await quality.getByText("Paper size").waitFor({ timeout: 40_000 });
    await quality.getByRole("radio", { name: "A4" }).check();
    await quality.getByRole("button", { name: "Continue" }).click();
    await quality
      .locator("li")
      .filter({ hasText: SHOP_NAME })
      .first()
      .getByRole("button", { name: "Choose this shop" })
      .click();
    await quality.getByRole("button", { name: "Continue to payment" }).click();
    const warning = quality.getByRole("region", { name: "File quality" });
    await warning
      .getByRole("heading", { name: /check your file quality/i })
      .waitFor({ timeout: 150_000 });
    if ((await warning.getByRole("alert").count()) > 0) {
      throw new Error(
        "the quality card shows an error; refusing to capture a broken page",
      );
    }
    await shot(quality, "10-quality-warning");
  });
  await qualityContext.close();

  await browser.close();

  console.log(`\n${done.length} screenshot(s) written to docs/screenshots/`);
  if (failed.length > 0) {
    console.log(`${failed.length} screen(s) could not be captured:`);
    for (const line of failed) console.log(`  - ${line}`);
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
