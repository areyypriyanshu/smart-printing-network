# Demo walkthrough

The [demo video](demo/spn-demo.mp4) is a screen recording of the real
product on a local Docker Compose stack, driven by Playwright. It runs
3 minutes 5 seconds and is not a mockup or an edited mockup: every
price, order number and pickup code comes from the running services, and
the two people in it are two browser contexts signed in as a seeded
vendor and a customer account created by the local way in.

The recording has burned-in captions, so it needs no voice track and no
separate subtitle file. This page is the written version.

## What happens, in order

| # | Scene | What it proves |
|---|---|---|
| 1 | Landing page | One origin serves the customer and the counter. |
| 2 | Sign in | The demo uses the local dev sign-in; in production the identity provider proves the account, and roles live in this database. |
| 3 | Shop search with a real file | Each shop returns the price of *this* file, computed by the same server function checkout uses, plus a queue-wait range from real events. |
| 4 | Print options | The price is computed on the server and the database has a `CHECK` constraint for it. |
| 5 | Payment | The fake payment gateway signs a real HMAC webhook; the browser is never believed about money. |
| 6 | Payment received | A signed webhook, verified on the raw body and deduplicated, is what marks the order paid. |
| 7 | Customer order page | The pickup code is the customer's proof; the shop does not see it before handover. |
| 8 | Quality check | The worker measures effective DPI and blur. The warning advises; it never blocks the order. |
| 9 | Vendor queue | The board is live over a WebSocket, and the same order is worked from the counter. |
| 10 | Accept | Accept is a compare-and-swap, so two shops clicking at once produce one winner. |
| 11 | Start and ready | The event timestamps feed the queue-wait estimate shown to the next customer. |
| 12 | Wrong pickup code | A wrong code is refused; five wrong tries in ten minutes are all an attacker gets. |
| 13 | Right pickup code | The order is collected, and the board and the customer agree. |
| 14 | Vendor rate card | The price starts at the shop's own rates, never at a number the customer sends. |
| 15 | Collected order | The customer's page shows the completed order and its full history. |
| 16 | My orders | Every order the customer has placed, with its status and pickup code while it is live. |
| 17 | Closing card | The measured test, coverage, CI and latency numbers. |

## What is real, and what is not

- **Real:** the API, PostgreSQL with PostGIS, the worker, object storage,
  price calculation, order state machine, pickup-code check, webhooks,
  WebSocket notifications and the frontend.
- **Fake by design:** the payment gateway. The demo runs the fake gateway
  in the same interface as Razorpay, with a real HMAC signature over the
  webhook, so the money path is exercised without moving money. Razorpay
  itself runs in test mode in this project.
- **Seeded:** three verified shops and the vendor accounts. `make seed`
  creates them; they are demo data, not real businesses. The customer
  account is created by the local dev sign-in on first use.
- **Simulated, and not shown as activity:** the queue-wait estimates in
  the demo use the shop's real order events. The longer backtest history
  in `make seed-history` is clearly labelled simulated and is not part of
  the video.

## Reproducing it

From the repository root:

```bash
make up && make migrate && make seed
cd e2e && npm ci
npx playwright install chrome        # once, if Chrome is not installed
node record-demo.mjs                 # writes docs/demo/spn-demo.mp4
```

`make demo` does the last step. The script records three browser parts
under `docs/demo/raw/` and uses `ffmpeg` to join them; if `ffmpeg` is
missing, the `.webm` parts are kept there and the previous video is left
in place. The stack is expected on `http://localhost:5173`, and
`E2E_BASE_URL` overrides it. Because the recorder creates accounts and
orders, a non-local host is refused unless `E2E_ALLOW_REMOTE=1` is set.

The same stack, seeded shops and vendor, and local dev customer produce
the screenshots in [`screenshots/`](screenshots/), with `make screenshots`.
See `e2e/capture-screenshots.mjs` and `e2e/record-demo.mjs` for the exact
selectors and timings.
