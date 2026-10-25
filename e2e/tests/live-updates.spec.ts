import {
  expect,
  test,
  type APIRequestContext,
  type WebSocketRoute,
} from "@playwright/test";

import { API_URL, signIn as signInHelper, signInAsCustomer } from "./helpers";

// The board goes live, and then the connection drops.
//
// A browser cannot hold a socket forever: a laptop sleeps, a network drops,
// a proxy restarts. When that happens the board must not go stale. It has to
// say that it is polling, keep reading the queue, and show a change made
// while it had no socket. That is the whole point of the fallback, so it is
// checked on the real board rather than only in a component test.
//
// The socket is intercepted through the browser rather than by stopping the
// API, so the polling path is exercised while the server is still perfectly
// healthy and reachable.

test.setTimeout(150_000);

const SHOP_NAME = "Central Prints";
const VENDOR_EMAIL = "vendor1@example.com";

/**
 * The shop's own access token, read the way the shop's browser gets one.
 *
 * The change below is made with this token instead of through the page, so
 * the board can only learn about it by polling. A click in the page would
 * refresh the board by itself and prove nothing about the fallback.
 */
async function vendorToken(request: APIRequestContext): Promise<string> {
  const login = await request.post(`${API_URL}/api/v1/auth/dev-session`, {
    data: { email: VENDOR_EMAIL },
  });
  return (await login.json()).access_token as string;
}

test("a dropped live socket falls back to polling and the board stays current", async ({
  browser,
  request,
}) => {
  // A reserved order this test made, so the board has a card to watch that
  // belongs to this run and not to whatever ran before it.
  const customerContext = await browser.newContext();
  const customer = await customerContext.newPage();
  await signInAsCustomer(customer);
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
  const shop = customer.locator("li").filter({ hasText: SHOP_NAME }).first();
  await expect(shop).toBeVisible();
  await shop.getByRole("button", { name: "Choose this shop" }).click();
  await customer.getByRole("button", { name: "Continue to payment" }).click();
  await customer.getByRole("radio", { name: /pay at the shop/i }).check();
  await customer.getByRole("button", { name: /reserve for/i }).click();
  await expect(customer.getByText("Reserved for you")).toBeVisible({
    timeout: 30_000,
  });
  const orderNumber = (
    await customer.getByText(/Order #\d+ is booked/).textContent()
  ).match(/#(\d+)/)?.[1];
  expect(orderNumber).toBeTruthy();

  // The board, with a working socket to begin with.
  const vendorContext = await browser.newContext();
  const vendor = await vendorContext.newPage();

  // The first sockets are let through to the server. Once the drop is
  // requested, every later attempt is refused, which is the network that
  // never comes back.
  let dropping = false;
  const openSockets: WebSocketRoute[] = [];
  await vendor.routeWebSocket(/\/ws\//, (socket) => {
    if (dropping) {
      socket.close();
      return;
    }
    openSockets.push(socket);
    socket.connectToServer();
  });

  const queueReads: number[] = [];
  vendor.on("request", (seen) => {
    if (seen.url().includes("/vendor/queue")) queueReads.push(Date.now());
  });

  await signInHelper(vendor, VENDOR_EMAIL);
  await vendor.goto("/vendor");

  const card = (column: string) =>
    vendor
      .getByRole("region", { name: column })
      .getByRole("article")
      .filter({ hasText: `#${orderNumber}` });

  await expect(card("New")).toBeVisible({ timeout: 25_000 });
  // The socket is up and the subscription is confirmed.
  await expect(vendor.getByText("Live updates on")).toBeVisible({
    timeout: 25_000,
  });

  // The connection drops, and it cannot be made again.
  dropping = true;
  for (const socket of openSockets) socket.close();
  await expect(vendor.getByText("Polling every 5 seconds")).toBeVisible({
    timeout: 30_000,
  });

  // Polling is actually running, not merely announced: the board keeps
  // reading the queue with no socket behind it.
  const before = queueReads.length;
  await expect
    .poll(() => queueReads.length, { timeout: 30_000 })
    .toBeGreaterThan(before);

  // A change made outside the page reaches the board, which can only have
  // read it back over the poll.
  const token = await vendorToken(request);
  const queue = await request.get(`${API_URL}/api/v1/vendor/queue`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const items = (
    (await queue.json()) as { items: { id: string; order_no: number }[] }
  ).items;
  const target = items.find((item) => String(item.order_no) === orderNumber);
  expect(target, "the order this test made is in the queue").toBeTruthy();

  const accepted = await request.post(
    `${API_URL}/api/v1/vendor/orders/${target?.id}/accept`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  expect(accepted.ok()).toBeTruthy();

  await expect(card("Accepted")).toBeVisible({ timeout: 30_000 });
  // It never went live again, because every socket is still refused.
  await expect(vendor.getByText("Live updates on")).toHaveCount(0);

  await vendorContext.close();
  await customerContext.close();
});
