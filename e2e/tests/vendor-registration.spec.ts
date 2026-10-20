import { expect, test } from "@playwright/test";

test("vendor completes all three registration steps", async ({ page }) => {
  const email = `vendor-e2e-${Date.now()}@example.com`;

  await page.goto("/register-vendor");

  await page.getByLabel("Shop name").fill("Kharghar E2E Print");
  await page
    .getByLabel("Shop address")
    .fill("Sector 12, Kharghar, Navi Mumbai");
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page.getByLabel("Latitude")).toBeVisible();
  await page.getByLabel("Latitude").fill("19.0473");
  await page.getByLabel("Longitude").fill("73.0699");
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page.getByLabel("Your name")).toBeVisible();
  await page.getByLabel("Your name").fill("E2E Vendor");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password", { exact: true }).fill("e2e-password-123");
  await page.getByRole("button", { name: "Register shop" }).click();

  await expect(page).toHaveURL(/\/login$/);
  // A confirmation is good news, so it is announced politely rather
  // than interrupting as an error would.
  await expect(page.getByRole("status")).toContainText("Account created");
});
