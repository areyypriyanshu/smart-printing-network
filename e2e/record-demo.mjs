// Records the demo video from a running stack.
//
//   make up && make migrate && make seed
//   SPN_DEV_AUTH=true VITE_SPN_DEV_AUTH=true docker compose up -d api frontend
//   cd e2e && npm ci && npx playwright install chrome
//   node record-demo.mjs
//
// It is a real recording of the real product: the customer uploads a
// file, compares the shops near them, pays through the fake gateway and
// is shown a pickup code; a deliberately low-resolution file shows the
// worker's quality warning; the shop works the order from the counter
// screen and hands it over; the customer sees the collected order. It
// closes on a card with the measured numbers. Three browser parts are
// recorded under docs/demo/raw, and ffmpeg joins them into
// docs/demo/spn-demo.mp4 when it is installed. The raw parts are kept
// either way, and the previous video is only replaced when the join
// succeeds.
//
// The demo uses the local way in and the fake payment gateway, which is
// what a local stack runs. The captions say so; they do not claim the
// identity provider or Razorpay are in this recording.
//
// The captions are injected into the page as it is driven, so the video
// explains itself without a voice track. Each scene is held long enough
// to read.

import { spawn } from "node:child_process";
import { mkdir, readdir, rm, rename } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = resolve(HERE, "..");
const OUT = resolve(REPO, "docs/demo");
const RAW = resolve(OUT, "raw");
const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:5173";

// The recorder creates accounts and orders, so it only drives a local
// stack unless the operator says otherwise.
if (
  !["localhost", "127.0.0.1", "[::1]"].includes(new URL(BASE_URL).hostname) &&
  process.env.E2E_ALLOW_REMOTE !== "1"
) {
  throw new Error(
    `refusing to drive ${BASE_URL}: the demo creates accounts and orders. Set E2E_ALLOW_REMOTE=1 to allow a non-local host.`,
  );
}

const CUSTOMER_EMAIL = "e2e-customer@example.com";
const VENDOR_EMAIL = "vendor1@example.com";
const SHOP_NAME = "Central Prints";
const KOLKATA = { latitude: 22.5726, longitude: 88.3639 };

const VIDEO = { width: 1280, height: 800 };

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const BANNER_CSS = `
  position: fixed; left: 24px; bottom: 24px; z-index: 2147483647;
  max-width: 780px; padding: 18px 24px; border-radius: 12px;
  background: rgba(17, 17, 17, 0.88); color: #fff;
  font: 500 26px/1.35 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  box-shadow: 0 8px 30px rgba(0,0,0,0.35); pointer-events: none;
`;

const TITLE_CSS = `
  position: fixed; inset: 0; z-index: 2147483647; display: flex;
  flex-direction: column; align-items: center; justify-content: center; gap: 18px;
  background: linear-gradient(160deg, #1b1b1f 0%, #2d2a26 100%); color: #fff;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  text-align: center; padding: 48px;
`;

/** A caption on the current page. Client-side routes keep it; a reload does not. */
async function caption(page, text) {
  await page.evaluate(
    ([css, value]) => {
      let el = document.getElementById("__demo_caption");
      if (!el) {
        el = document.createElement("div");
        el.id = "__demo_caption";
        el.style.cssText = css;
        document.body.appendChild(el);
      }
      el.textContent = value;
    },
    [BANNER_CSS, text],
  );
}

/** A full-screen title card for the start and the halfway mark. */
async function titleCard(page, heading, sub) {
  await page.setContent(
    `<!doctype html><html><body style="margin:0">
      <div style="${TITLE_CSS}">
        <div style="font-size:54px;font-weight:700;letter-spacing:-1px">${heading}</div>
        <div style="font-size:24px;opacity:0.75;max-width:760px;line-height:1.4">${sub}</div>
      </div>
    </body></html>`,
  );
}

async function signIn(page, email) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL((url) => !url.pathname.endsWith("/login"), { timeout: 30_000 });
}

async function record(name, fn) {
  const context = await chromium.launch({ channel: "chrome" }).then(async (browser) => {
    const ctx = await browser.newContext({
      viewport: VIDEO,
      baseURL: BASE_URL,
      geolocation: KOLKATA,
      permissions: ["geolocation"],
      recordVideo: { dir: RAW, size: VIDEO },
    });
    ctx.__browser = browser;
    return ctx;
  });
  const page = await context.newPage();
  try {
    await fn(page);
  } finally {
    const video = page.video();
    await context.close();
    await context.__browser.close();
    if (video) {
      const raw = await video.path();
      const target = resolve(RAW, `${name}.webm`);
      await rm(target, { force: true });
      await rename(raw, target);
      console.log(`recorded docs/demo/raw/${name}.webm`);
    }
  }
}

async function customerJourney(page) {
  await titleCard(
    page,
    "Smart Printing Network",
    "Upload a document, see the price from a real shop, pay, and collect with a pickup code.",
  );
  await sleep(5000);

  await page.goto("/");
  await caption(page, "One origin: the customer and the counter use the same site.");
  await sleep(7000);

  await page.goto("/login");
  await caption(page, "The demo uses the local way in. In production the identity provider proves the account; the rules live in our database.");
  await sleep(5000);
  await signIn(page, CUSTOMER_EMAIL);

  await page.goto("/shops");
  await caption(page, "Shops near the customer, with the real price per page and the current queue wait.");
  await page.getByRole("button", { name: /find shops near me/i }).click();
  await page
    .locator("li")
    .filter({ hasText: SHOP_NAME })
    .first()
    .waitFor({ timeout: 30_000 });
  await sleep(5000);

  await caption(page, "Choosing a file asks each shop what it would charge — through the same pricing function checkout uses.");
  await page.locator('input[type="file"]').setInputFiles("tests/fixtures/one-page.pdf");
  await page.getByText(/one-page\.pdf/).waitFor({ timeout: 30_000 });
  await page.getByText(/Current queue wait:/).first().waitFor({ timeout: 30_000 });
  await sleep(9000);

  await page
    .locator("li")
    .filter({ hasText: SHOP_NAME })
    .first()
    .getByRole("button", { name: /order from this shop/i })
    .click();
  await page.getByText("Paper size").waitFor({ timeout: 30_000 });
  await caption(page, "Print options. The price is computed on the server and checked again by a database constraint.");
  await page.getByRole("radio", { name: "A4" }).check();
  await page.getByLabel("Print in colour").check();
  await page.getByLabel("Copies").fill("2");
  await sleep(8000);
  await page.getByRole("button", { name: "Continue" }).click();

  await page
    .locator("li")
    .filter({ hasText: SHOP_NAME })
    .first()
    .getByRole("button", { name: "Choose this shop" })
    .click();
  await page.getByRole("button", { name: "Continue to payment" }).click();
  await page.getByRole("button", { name: /^Pay /i }).waitFor({ timeout: 30_000 });
  await caption(page, "The fake payment gateway signs a real webhook. The browser is never believed about money.");
  await sleep(6000);

  await page.getByRole("button", { name: /^Pay /i }).click();
  await page.getByText("Payment received").waitFor({ timeout: 45_000 });
  await caption(page, "A signed webhook, verified on the raw bytes and deduplicated, is what marks an order paid.");
  await sleep(10000);

  await page.getByRole("link", { name: "View order" }).click();
  await page.waitForURL(/\/orders\//, { timeout: 30_000 });
  await caption(page, "The pickup code is the customer's proof. The shop never sees it before the handover.");
  const pickupCode = (
    await page.getByRole("region", { name: "Pickup code" }).locator("p").first().innerText()
  ).trim();
  const text = await page.locator("body").innerText();
  const orderNumber = text.match(/ORDER\s*#\s*(\d+)/i)?.[1] ?? null;
  const orderUrl = page.url();
  await sleep(10000);

  // A second, deliberately low-resolution file shows the quality check.
  // The warning is produced by the worker and advises; it does not block.
  await page.goto("/new");
  await page.locator('input[type="file"]').setInputFiles("tests/fixtures/low-resolution.pdf");
  await page.getByText("Paper size").waitFor({ timeout: 40_000 });
  await page.getByRole("radio", { name: "A4" }).check();
  await page.getByRole("button", { name: "Continue" }).click();
  await page
    .locator("li")
    .filter({ hasText: SHOP_NAME })
    .first()
    .getByRole("button", { name: "Choose this shop" })
    .click();
  await page.getByRole("button", { name: "Continue to payment" }).click();
  await page
    .getByRole("region", { name: "File quality" })
    .getByRole("heading", { name: /check your file quality/i })
    .waitFor({ timeout: 150_000 });
  const qualityAlert = page
    .getByRole("region", { name: "File quality" })
    .getByRole("alert");
  if ((await qualityAlert.count()) > 0) {
    throw new Error(
      "the quality card shows an error, so the recording would ship a broken page",
    );
  }
  await caption(page, "The worker measures effective DPI and blur. The warning advises; it never blocks the order.");
  await sleep(9000);

  return { orderUrl, pickupCode, orderNumber };
}

async function vendorJourney(page, orderNumber, pickupCode) {
  await titleCard(
    page,
    "The counter screen",
    "The same order, worked by the shop from the queue to the handover.",
  );
  await sleep(5000);

  await signIn(page, VENDOR_EMAIL);
  await page.goto("/vendor");
  await caption(page, "The board updates over a WebSocket; polling is the fallback when the socket drops.");
  const column = (name) =>
    page.getByRole("region", { name }).getByRole("article").filter({ hasText: `#${orderNumber}` });
  await column("New").waitFor({ timeout: 30_000 });
  await sleep(6000);

  await column("New").getByRole("button", { name: "Accept" }).click();
  await column("Accepted").waitFor({ timeout: 20_000 });
  await caption(page, "Accept is a compare-and-swap: two shops clicking at once produce one winner, not two.");
  await sleep(5000);

  await column("Accepted").getByRole("button", { name: "Start printing" }).click();
  await column("Printing").waitFor({ timeout: 20_000 });
  await caption(page, "Start and Ready timestamps feed the queue-wait estimate shown to the next customer.");
  await sleep(5000);

  await column("Printing").getByRole("button", { name: "Mark ready" }).click();
  await column("Ready").waitFor({ timeout: 20_000 });
  await caption(page, "Ready for pickup. The customer's page hears about it without a refresh.");
  await sleep(5000);

  await column("Ready").getByRole("button", { name: "Verify pickup" }).click();
  await page.getByLabel("Pickup code").fill("000000");
  await page.getByRole("button", { name: "Hand over" }).click();
  await page.getByRole("alert").waitFor({ timeout: 15_000 });
  await caption(page, "A wrong code is refused; five wrong tries in ten minutes are all an attacker gets.");
  await sleep(5000);

  await page.getByLabel("Pickup code").fill(pickupCode);
  await page.getByRole("button", { name: "Hand over" }).click();
  await column("Ready").waitFor({ state: "detached", timeout: 20_000 });
  await caption(page, "With the right code the order is collected. The board and the customer's page agree.");
  await sleep(5000);

  await page.goto("/vendor/rates");
  await page.getByRole("heading", { name: "Rates" }).waitFor({ timeout: 30_000 });
  await caption(page, "The price starts here: the shop's own rate card, never a number the customer sends.");
  await sleep(8000);
}

async function collectedJourney(page, orderUrl) {
  await signIn(page, CUSTOMER_EMAIL);
  await page.goto(orderUrl);
  await page.getByRole("heading", { name: "Collected", exact: false }).waitFor({ timeout: 30_000 });
  await caption(page, "The same order, from the customer's side: collected, with its full history.");
  await sleep(9000);
  await page.goto("/orders");
  await page.getByRole("heading", { name: "My orders" }).waitFor({ timeout: 30_000 });
  await caption(page, "Every order the customer has placed, with its status and pickup code while it is live.");
  await sleep(8000);
  await titleCard(
    page,
    "Money and state are the hard part",
    "A signed webhook decides payment. One function changes status. The database checks the price. Every step is tested.",
  );
  await sleep(7000);
  await titleCard(
    page,
    "By the numbers",
    "819 backend tests and 168 frontend tests. 91.7% statement coverage. CI green in 3m53s. Quote p95 25.8 ms with 238 orders in the queue.",
  );
  await sleep(8000);
}

async function main() {
  // Record into docs/demo/raw. The published video is only replaced by
  // the ffmpeg step at the end, so a failed take leaves the old one in
  // place.
  await rm(RAW, { recursive: true, force: true });
  await mkdir(RAW, { recursive: true });

  let result = null;
  await record("part-1-customer", async (page) => {
    result = await customerJourney(page);
  });

  if (result === null || result.orderNumber === null || result.pickupCode === "") {
    throw new Error(
      "the order number or pickup code could not be read, so the vendor scene would not know what to work",
    );
  }
  const { orderNumber, orderUrl, pickupCode } = result;

  await record("part-2-vendor", async (page) => {
    await vendorJourney(page, orderNumber, pickupCode);
  });

  await record("part-3-collected", async (page) => {
    await collectedJourney(page, orderUrl);
  });

  // Join the parts, if ffmpeg is here. The parts are kept either way.
  const parts = [
    resolve(RAW, "part-1-customer.webm"),
    resolve(RAW, "part-2-vendor.webm"),
    resolve(RAW, "part-3-collected.webm"),
  ];
  const final = resolve(OUT, "spn-demo.mp4");
  const joined = resolve(RAW, "spn-demo.mp4");
  try {
    await run("ffmpeg", [
      "-y",
      "-i",
      parts[0],
      "-i",
      parts[1],
      "-i",
      parts[2],
      "-filter_complex",
      "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
      "-map",
      "[v]",
      "-c:v",
      "libx264",
      "-pix_fmt",
      "yuv420p",
      "-crf",
      "26",
      "-movflags",
      "+faststart",
      joined,
    ]);
    // Join into the work directory, then replace the published file in
    // one step, so a failed encode leaves the previous video untouched.
    await rename(joined, final);
    console.log(`\nwrote docs/demo/spn-demo.mp4`);
  } catch {
    await rm(joined, { force: true });
    console.log(
      "\nffmpeg is not installed or the join failed, so the three .webm parts were kept in docs/demo/raw/.",
    );
    console.log(`files: ${(await readdir(RAW)).join(", ")}`);
  }
}

function run(command, args) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(command, args, { stdio: ["ignore", "ignore", "pipe"] });
    let stderr = "";
    child.stderr.on("data", (chunk) => {
      stderr += chunk;
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) resolvePromise(undefined);
      else reject(new Error(`${command} exited ${code}: ${stderr.slice(-400)}`));
    });
  });
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
