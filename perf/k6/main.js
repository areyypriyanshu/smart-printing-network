/**
 * The load the phase 2 gate asks for: quotes, shop search and the vendor
 * queue, measured against a running stack.
 *
 * The script signs in through the local way in, because it has to run
 * offline and the same way every time. That route is refused in
 * production. Run it against `make up`, never against a deployment.
 *
 * Each virtual user is a different account. The rate limiter is per
 * account, so sharing one account would measure the limiter rather than
 * the endpoint. The default rates stay under the limits in the router:
 * quotes 60 a minute, shop search 30 a minute and the queue 60 a minute.
 *
 * See perf/k6/README.md for the commands and perf/BASELINE.md for the
 * numbers this produced.
 */

import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const API = `${BASE_URL}/api/v1`;

//: How many accounts the script makes, one per virtual user. More
//: accounts allow a higher rate without touching the per-account limit.
const CUSTOMERS = Number(__ENV.CUSTOMERS || 4);

//: One virtual user is one account. The pace is per user, so the
//: per-account rate limiter is never the thing being measured: a quote
//: every second is the 60 a minute the router allows, and a search
//: every two seconds is half of the 30 a minute it allows. Raise the
//: pace and more accounts are needed, not a bigger sleep.
const QUOTES_EVERY = Number(__ENV.QUOTES_EVERY || 1);
const SEARCH_EVERY = Number(__ENV.SEARCH_EVERY || 2);
const QUEUE_EVERY = Number(__ENV.QUEUE_EVERY || 1);
const DURATION = __ENV.DURATION || "30s";

const VENDOR_EMAIL = __ENV.VENDOR_EMAIL || "vendor1@example.com";

//: A real one page PDF. The upload endpoint checks the bytes, so a
//: string named .pdf would not do.
const PDF = open("../../e2e/tests/fixtures/one-page.pdf", "b");

export const options = {
  scenarios: {
    quotes: {
      executor: "constant-vus",
      exec: "quotes",
      vus: CUSTOMERS,
      duration: DURATION,
      tags: { endpoint: "quotes" },
    },
    search: {
      executor: "constant-vus",
      exec: "search",
      vus: CUSTOMERS,
      duration: DURATION,
      tags: { endpoint: "shop-search" },
    },
    queue: {
      executor: "constant-vus",
      exec: "queue",
      vus: 1,
      duration: DURATION,
      tags: { endpoint: "vendor-queue" },
    },
  },
  thresholds: {
    // A failed request is a failed gate. A 429 here means the script
    // asked for more than the account is allowed, not that the endpoint
    // is slow.
    http_req_failed: ["rate==0"],
    // The non-functional requirements in the PRD.
    "http_req_duration{endpoint:quotes}": ["p(95)<200"],
    "http_req_duration{endpoint:vendor-queue}": ["p(95)<300"],
    // The search has no number of its own in the PRD. It is held to the
    // same order of magnitude as the queue because it does more work:
    // the spatial query, the rate join and the price of every shop.
    "http_req_duration{endpoint:shop-search}": ["p(95)<500"],
  },
};

function bearer(token) {
  return { Authorization: `Bearer ${token}` };
}

function jsonHeaders(token) {
  return { ...bearer(token), "Content-Type": "application/json" };
}

function devSession(body) {
  const response = http.post(
    `${API}/auth/dev-session`,
    JSON.stringify(body),
    { headers: { "Content-Type": "application/json" } },
  );
  if (response.status !== 200) {
    throw new Error(
      `The local way in is not available (${response.status}). ` +
        "Set SPN_DEV_AUTH=true in .env, restart the stack, and run `make seed`.",
    );
  }
  return response.json().access_token;
}

export function setup() {
  const customers = [];
  for (let index = 0; index < CUSTOMERS; index += 1) {
    const token = devSession({
      email: `perf-load-${index}@example.com`,
      full_name: `Load Test Customer ${index}`,
      role: "customer",
    });
    const upload = http.post(
      `${API}/uploads`,
      { file: http.file(PDF, "load-test.pdf", "application/pdf") },
      { headers: bearer(token) },
    );
    if (upload.status !== 201) {
      throw new Error(
        `The upload for customer ${index} failed (${upload.status}): ${upload.body}`,
      );
    }
    customers.push({ token, uploadId: upload.json().id });
  }

  const search = http.get(
    `${API}/shops/search?latitude=22.5726&longitude=88.3639&radius_m=50000&limit=50`,
    { headers: bearer(customers[0].token) },
  );
  if (search.status !== 200) {
    throw new Error(`The shop search failed (${search.status}): ${search.body}`);
  }
  const shops = search.json().items;
  if (shops.length === 0) {
    throw new Error("No shops. Run `make seed` before the load test.");
  }

  const vendorToken = devSession({
    email: VENDOR_EMAIL,
    full_name: "Load Test Vendor",
    role: "vendor",
  });
  const queue = http.get(`${API}/vendor/queue`, {
    headers: bearer(vendorToken),
  });
  if (queue.status !== 200) {
    throw new Error(
      `The vendor queue failed (${queue.status}). ` +
        `Is ${VENDOR_EMAIL} a seeded vendor account?`,
    );
  }

  return {
    customers,
    shopId: shops[0].id,
    vendorToken,
  };
}

function customerFor(data) {
  return data.customers[__VU % data.customers.length];
}

export function quotes(data) {
  const customer = customerFor(data);
  const response = http.post(
    `${API}/quotes`,
    JSON.stringify({
      upload_id: customer.uploadId,
      shop_id: data.shopId,
      paper_size: "A4",
      color: false,
      duplex: false,
      copies: 1,
    }),
    { headers: jsonHeaders(customer.token), tags: { endpoint: "quotes" } },
  );

  check(response, {
    "the quote is priced": (result) => result.status === 200,
    "the price is a whole number of paise": (result) =>
      Number.isInteger(result.json().price_paise),
  });
  sleep(QUOTES_EVERY);
}

export function search(data) {
  const customer = customerFor(data);
  // k6 has no URLSearchParams, so the query is written out. Every
  // value is fixed except the upload id, which is a UUID and is
  // escaped anyway.
  const query = [
    "latitude=22.5726",
    "longitude=88.3639",
    "radius_m=50000",
    "sort=price",
    "limit=50",
    `upload_id=${encodeURIComponent(customer.uploadId)}`,
    "paper_size=A4",
    "color=false",
    "duplex=false",
    "copies=1",
  ].join("&");
  const response = http.get(`${API}/shops/search?${query}`, {
    headers: bearer(customer.token),
    tags: { endpoint: "shop-search" },
  });

  check(response, {
    "the search answers": (result) => result.status === 200,
    "every shop has a price": (result) => {
      const body = result.json();
      return (
        Array.isArray(body.items) &&
        body.items.every((item) => Number.isInteger(item.price_paise))
      );
    },
  });
  sleep(SEARCH_EVERY);
}

export function queue(data) {
  const response = http.get(`${API}/vendor/queue?limit=100`, {
    headers: bearer(data.vendorToken),
    tags: { endpoint: "vendor-queue" },
  });

  check(response, {
    "the queue answers": (result) => result.status === 200,
    "the queue has a list": (result) => Array.isArray(result.json().items),
  });
  sleep(QUEUE_EVERY);
}
