# Engineering decisions

A short version of *why* this project is built the way it is. The long
version is in the architecture decision records in [`adr/`](adr/), one file
per decision, each with the context, the decision, the alternatives that
were rejected, the consequences and a trigger for revisiting it.

The project is a print shop marketplace: a customer uploads a PDF, picks
print options, sees the price from a shop's own rate card, pays, and
collects the printout with a six digit pickup code. The shop works a
queue of paid orders from a counter screen.

The interesting part of this project is not the screens. It is that money
moves only when the state machine says so, and that the rules are
enforced in more than one place.

---

## The five decisions that shape everything else

### 1. The webhook, not the browser, decides that an order is paid

The browser can be closed, offline, or lying. A signed webhook is
verified against the **raw request body** with a constant time
comparison, deduplicated by the provider's event id, and checked for the
amount and the currency before anything is marked as paid. A late payment
on an expired order is refunded automatically.
[ADR 004](adr/004-webhook-is-the-source-of-truth.md),
[ADR 005](adr/005-text-and-check-constraints.md)

The event and the effect it causes are one transaction, so a delivery
that failed is not spent and a capture is never left behind without an
order.
[ADR 022](adr/022-the-webhook-event-and-its-effect-are-one-transaction.md)

### 2. One function changes an order's status, and the database checks the price

`order_service.transition()` is the only place in the application that
writes `orders.status`. It does a compare and swap
(`UPDATE ... WHERE status = :from`), so two shops clicking Accept at the
same moment produce one winner and one `CONFLICT`, without a lock. The
status change and its `order_events` row commit together.

The price is `max(pages x copies x rate, shop minimum)`, and the database
refuses to store anything else:

```sql
CHECK (price_paise = GREATEST(page_count * copies * rate_paise, min_order_paise))
```

A bug in the application cannot produce a wrong price.
[ADR 010](adr/010-price-invariant-enforced-by-the-database.md)

### 3. The domain layer is pure, and that is enforced

`app/domain/` is three small files with no imports outside the standard
library. An import linter contract fails the build if it ever imports
SQLAlchemy, FastAPI, Pydantic or anything from the rest of the app. The
pricing rule, the state machine and the refund backoff schedule are
therefore testable without a database, an event loop or a mock.
[ADR 001](adr/001-fastapi-over-node-express.md),
[ADR 002](adr/002-sync-sqlalchemy-plain-def-endpoints.md)

### 4. The payment provider sits behind an interface, with a real fake

`PaymentGateway` is a `Protocol`. `RazorpayGateway` uses `urllib` from
the standard library rather than adding a dependency, and `FakeGateway`
signs real HMAC webhooks. The whole test suite, the local stack and the
demo run against the fake, so the money path is exercised the same way in
every environment.
[ADR 009](adr/009-payment-gateway-interface.md),
[ADR 010](adr/010-price-invariant-enforced-by-the-database.md)

### 5. Background work is database driven, with no broker

Expiring unpaid orders, rejecting orders no shop picked up, retrying
refunds and deleting old files are four functions that query Postgres,
claim rows with `FOR UPDATE SKIP LOCKED`, and update them conditionally.
There is no Redis, no Celery and no separate queue to run, monitor or
debug. A second worker is safe by construction.
[ADR 003](adr/003-database-driven-jobs.md),
[ADR 008](adr/008-single-instance-docker-compose.md)

---

## What was deliberately left out

The original idea promised more than is sensible to build, and the
decisions that keep this project honest are mostly about what not to
build.

| Left out | Why |
|---|---|
| Delivery, couriers, route optimisation | Needs live location and failure handling. Pickup only. |
| A CNN for blur detection | No labelled dataset and no evaluation. Effective DPI plus Laplacian variance on a labelled fixture set answers the same question and can be explained. |
| Machine learning for price or wait estimates | Price is arithmetic. Wait estimates start as a rolling median and are only replaced by a model if they measurably lose to it on real data. |
| Vendor payouts, GST invoicing | Marketplace money movement needs KYC, split payments and legal review. |
| Email and SMS notifications | In app status only, for now. |
| Page ranges, binding, multi file orders | Whole document printing only. |
| Kubernetes, Redis, a managed database | One instance is enough, and each would add cost and failure modes without users to justify them. |

The full list of non goals, with the reasoning, is in the product
requirements document. The two decisions that shape the later phases are
[ADR 006](adr/006-classical-image-analysis-not-a-cnn.md), which rules out
a neural network for the quality checker, and
[ADR 007](adr/007-polling-before-websockets.md), which rules out a
WebSocket until there is something worth pushing.

### The admin panel is narrow on purpose

There is an admin role, and it can do two things: approve a shop and
suspend a shop. It cannot read a customer's order, a customer's file, or
any money, and there is no admin endpoint that could.

That restraint is the point. A verification queue is the job, and every
table that becomes browsable is a table whose data can leak. An admin
account is created from the command line, never over HTTP, because an
admin is the person who decides which shops are allowed to take orders.

A suspension takes a shop off the market without touching its existing
orders: a customer who has already paid is owed that printout, and the
shop that is printing it still has to be able to finish it. Every
decision is recorded in `admin_actions`, with the admin, the shop, the
time and the reason.
[ADR 014](adr/014-admin-panel.md)

---

## The file the student actually has

The product says "upload a PDF". The student has a Word document, and
the old answer was a dead end: "File does not look like a PDF." A dead
end is a message that does not say what to do, and a customer who hits
one does not come back.

Two things changed. The first is that every file the platform cannot
print is now refused with a message that names the fix, because the
server knows what the file actually was and the client does not. The
second is that a Word, Excel or PowerPoint file is accepted, converted
to a PDF on the server, and printed as one.

The conversion is built on what is already in the image: the standard
library reads the office formats, and PyMuPDF's `Story` engine lays them
out. No new dependency, no new service, no new image. What it does not
keep is said plainly in the product: the fonts are substituted, the
tables are re-laid out, and the headers, footers and columns are gone.
A converted document is a printable approximation of the document the
student made, not a copy of it, and the upload screen says so.

Two more decisions came out of the same conversation.

**Printing it again copies the file, it does not share it.** The
platform promises to delete a customer's file 24 hours after the
upload. A one-tap reprint has to respect that promise, so it copies the
object to a new key with a new retention window. After the window, the
answer is "upload it again", which is the honest one.
[ADR 017](adr/017-print-it-again.md)

**The pickup code is a bearer token, and saying so is part of the
feature.** The customer can share it on WhatsApp with a plain `wa.me`
link, with no business API and no cost. Whoever has the code can
collect the printout, so the interface says that next to the button
rather than in a policy page.
[ADR 018](adr/018-sharing-the-pickup-code.md)

**A login is rate limited per account as well as per address.** Ten
guesses a minute against one account stops a brute force. Ten logins a
minute for a whole address locks out a college, because a campus shares
one address. The end-to-end suite found this by tripping it.
[ADR 019](adr/019-rate-limiting-a-login-per-account.md)

**A value the database cannot hold is refused at the door.** A NUL byte
in an email, a name or a file name used to reach the insert and be
refused by PostgreSQL, which the person typing saw as a 500. Every
string written to the database is checked at the boundary, a value the
database still refuses is a 422 rather than a 500, and a 500 carries the
request id so it can be found in the logs.
[ADR 024](adr/024-the-boundary-refuses-a-value-the-database-cannot-hold.md)

**The deployment caps the work it will do, not only the attacker's
share of it.** Creating an account hashes a password, and that is CPU
the server cannot refuse once it has started it. There are four limits
on registration, and the last one is per deployment rather than per
caller: sixty accounts a minute, however many machines are asking.
[ADR 025](adr/025-the-limits-on-creating-an-account.md)

**An email address is a claim until it is proved.** A link is sent to
the address, and opening it proves it. The account works while it is
unproved, but it cannot order a print, because the printout and the
pickup code are tied to the address. A customer who typed the address
wrong can put the right one there, which is the only way out of a
mistyped address.
[ADR 026](adr/026-the-email-address-has-to-be-proved.md)

[ADR 016](adr/016-office-file-upload.md) has the full reasoning for the
conversion, including the alternatives that were rejected and why.

---

## How the rules are tested

The rules above are not comments. Each one has a test that fails if the
rule is broken.

| Rule | How it is proved |
|---|---|
| No illegal transition is reachable | An exhaustive table over every pair of statuses, and a property test that walks random transition attempts. |
| A status change and its history entry happen together | The event insert is broken on purpose and the test asserts the status rolled back with it. |
| The price rule holds | The database is asked to store a wrong price and refuses. |
| The pickup code never changes | The order is driven through the whole lifecycle and the code is compared at the end. |
| The shop never sees the pickup code | The real code is read out of the response body and the test fails if it is there. |
| A webhook is only believed once | Two threads deliver the same event at the same time; the test asserts one capture, one transition, one event row. |
| The vendor cannot see another shop's order | The other shop's order returns 404, not 403, so the response never confirms that it exists. |
| A pickup code cannot be guessed | Five wrong codes are allowed, the sixth is rate limited. |
| A job can run twice | Every job is run twice and the second run has to do nothing. |
| A backup is real | A dump is restored into a scratch database and the restored data is checked against the price rule. |
| The API matches its own contract | The API is fuzzed from its own OpenAPI schema. It found a real bug: registering a shop with an email that already existed returned a 500 instead of a 409. |
| A file that cannot be printed says what to do | Every file kind has a test that the refusal names the fix, not just the problem. |
| A converted document is a PDF | The stored object is read back and has to start with `%PDF-`, and the shop's download has to be named `report.pdf` for a `report.docx`. |
| A reprint never breaks the retention promise | The two uploads are shown to have different storage keys and different retention windows, and a reprint after the purge answers `FILE_UNAVAILABLE`. |
| A shop's phone number is optional and sane | The database is asked to store a number with too few digits, too many digits and letters, and refuses all three. |

---

## The stack, and why each piece is here

| Piece | Choice | Why |
|---|---|---|
| Backend | Python 3.12, FastAPI | The PDF and image work in Phase 2 is Python. One language, one test runner, one deployment. |
| Database | PostgreSQL with PostGIS | The data is relational and money related, and needs transactions, constraints and a spatial index. |
| Object storage | S3, with MinIO locally | The bucket is private, so every download is a five minute presigned link. |
| Frontend | React, TypeScript, Vite, TanStack Query | Server state in one place, types generated from the API contract rather than written by hand. |
| Dialogs | The native `<dialog>` element | Focus trapping, Escape, an inert background and the top layer come from the browser, so there is no library to depend on. See [ADR 021](adr/021-native-dialog-element.md). |
| Jobs | A worker container polling Postgres | Four periodic jobs do not need a broker. |
| Contracts | `openapi-typescript`, a drift check in CI, and a fuzzer | The frontend cannot silently drift from the backend. |
| Deploy | One instance, Docker Compose, Caddy | Cheap, understandable, and it makes the whole path inspectable. |
| Local database browser | pgAdmin in Compose, behind a profile | A reviewer can open the tables and the rows without installing a client. It is a development tool: it is never deployed, and CI never pulls it. See [ADR 015](adr/015-database-browser-for-local-development.md). |

The reasoning and the rejected alternatives for each of these are in
[`adr/`](adr/) and in the technology stack document.

---

## What is not done yet

Being honest about the edges is part of explaining the design.

- Payments run in test mode. No real money moves and vendor payouts do
  not exist.
- There is no page range, no binding and no multi file order.
- One order per upload, one upload per order. A customer who abandons a
  payment starts again with a new upload.
- The rate limiter lives in the process, so a second API instance would
  need Redis. The deployment is one instance.
- The queue polls every five seconds. WebSockets arrive in the phase where
  a live board actually needs them.
- The PDF quality checker and the map view are not built. They are the
  next phase and they are deliberately the next phase. The list of shops
  near the customer is built, without the map.
- A converted Word, Excel or PowerPoint file keeps the text, the
  headings, the pictures and the table contents. It does not keep the
  fonts, the exact table widths, the headers, the footers or the
  columns. A student who needs the exact layout uploads a PDF.
