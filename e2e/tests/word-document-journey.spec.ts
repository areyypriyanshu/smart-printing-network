import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

import { API_URL, signIn as signInHelper, signInAsCustomer } from "./helpers";

// A student uploads the file they actually have.
//
// Most students have a Word document, not a PDF. The platform reads it,
// turns it into a PDF and prints that, so the journey is the same as
// for a PDF, and the file the shop opens is a PDF.

// The worker turns the document into a PDF in the background, and it
// looks at the queue every thirty seconds, so the file can take a
// minute to arrive. The test's own limit is longer than that.
test.setTimeout(120_000);

const SHOP_NAME = "Central Prints";
const VENDOR_EMAIL = "vendor1@example.com";

/**
 * The link the shop would open for an order, read through the API the
 * shop uses.
 *
 * The link names the file, and the name is the point: a customer who
 * sent a Word document must not hand the shop a file called
 * "report.docx" that is really a PDF.
 */
async function printedFileLink(
  request: APIRequestContext,
  orderId: string,
): Promise<string> {
  const login = await request.post(`${API_URL}/api/v1/auth/dev-session`, {
    data: { email: VENDOR_EMAIL },
  });
  const token = (await login.json()).access_token as string;

  // The file the shop opens is a PDF, and it is a PDF only after the
  // worker has converted the document. The worker runs every thirty
  // seconds, so the link is asked for until it is there rather than
  // once and hoped for. The route is rate limited, so the attempts are
  // spaced out and few.
  for (let attempt = 0; attempt < 20; attempt++) {
    const link = await request.get(
      `${API_URL}/api/v1/vendor/orders/${orderId}/file`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    const body = (await link.json()) as { url?: string };
    if (typeof body.url === "string") return body.url;
    await new Promise((resolve) => setTimeout(resolve, 3000));
  }
  throw new Error("the printed file never became available to the shop");
}

test("a Word document is printed like any other file", async ({
  browser,
  request,
}) => {
  const customerContext = await browser.newContext();
  const customer = await customerContext.newPage();
  await signInAsCustomer(customer);

  // The customer uploads a Word document.
  await customer.goto("/new");
  await customer
    .locator('input[type="file"]')
    .setInputFiles("tests/fixtures/report.docx");
  await expect(customer.getByText("Paper size")).toBeVisible({
    timeout: 30_000,
  });

  await customer.getByRole("radio", { name: "A4" }).check();
  await customer.getByLabel("Copies").fill("1");
  await customer.getByRole("button", { name: "Continue" }).click();

  const shop = customer.locator("li").filter({ hasText: SHOP_NAME }).first();
  await expect(shop).toBeVisible();
  await shop.getByRole("button", { name: "Choose this shop" }).click();
  await customer.getByRole("button", { name: "Continue to reserve" }).click();
  await customer.getByRole("button", { name: /^Reserve for /i }).click();

  await expect(customer.getByText("Reserved for you")).toBeVisible({
    timeout: 30_000,
  });
  const orderNumber = (
    await customer.getByText(/Order #\d+ is booked/).textContent()
  ).match(/#(\d+)/)?.[1];
  expect(orderNumber).toBeTruthy();
  const orderId = (
    await customer
      .getByRole("link", { name: "View order" })
      .getAttribute("href")
  )
    ?.split("/")
    .pop();
  expect(orderId).toBeTruthy();

  // The shop works the order as it would any other, and the file it
  // opens is a PDF even though the customer sent a Word document.
  const vendorContext = await browser.newContext();
  const vendor = await vendorContext.newPage();
  await signInHelper(vendor, VENDOR_EMAIL);
  await vendor.goto("/vendor");

  // The card is found by the order number, so another order in the
  // queue does not get in the way.
  const thisOrder = (region: string) =>
    vendor
      .getByRole("region", { name: region })
      .getByRole("article")
      .filter({ hasText: `#${orderNumber}` });
  await expect(thisOrder("New")).toBeVisible({ timeout: 15_000 });
  await thisOrder("New").getByRole("button", { name: "Accept" }).click();
  await expect(thisOrder("Accepted")).toBeVisible({ timeout: 15_000 });
  await thisOrder("Accepted")
    .getByRole("button", { name: "Start printing" })
    .click();
  await expect(thisOrder("Printing")).toBeVisible({ timeout: 15_000 });
  await thisOrder("Printing")
    .getByRole("button", { name: "Mark ready" })
    .click();
  await expect(thisOrder("Ready")).toBeVisible({ timeout: 15_000 });

  const readyCard = thisOrder("Ready");
  await expect(readyCard).toBeVisible({ timeout: 15_000 });

  // The file the shop opens is a PDF, even though the customer sent a
  // Word document. The shop's machine has to be able to open it.
  const link = await printedFileLink(request, orderId as string);
  expect(decodeURIComponent(link)).toContain('filename="report.pdf"');

  await vendorContext.close();
  await customerContext.close();
});

test("a file we cannot print says how to fix it", async ({ browser }) => {
  const customerContext = await browser.newContext();
  const customer = await customerContext.newPage();
  await signInAsCustomer(customer);

  await customer.goto("/new");
  await customer
    .locator('input[type="file"]')
    .setInputFiles("tests/fixtures/screenshot.png");

  // The message names the fix, not just the problem.
  await expect(customer.getByText(/Download as PDF/i)).toBeVisible({
    timeout: 30_000,
  });

  await customerContext.close();
});
