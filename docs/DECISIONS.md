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
| An admin interface | Shop verification is a CLI command. |
| Page ranges, binding, multi file orders | Whole document printing only. |
| Kubernetes, Redis, a managed database | One instance is enough, and each would add cost and failure modes without users to justify them. |

The full list of non goals, with the reasoning, is in the product
requirements document. The two decisions that shape the later phases are
[ADR 006](adr/006-classical-image-analysis-not-a-cnn.md), which rules out
a neural network for the quality checker, and
[ADR 007](adr/007-polling-before-websockets.md), which rules out a
WebSocket until there is something worth pushing.

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

---

## The stack, and why each piece is here

| Piece | Choice | Why |
|---|---|---|
| Backend | Python 3.12, FastAPI | The PDF and image work in Phase 2 is Python. One language, one test runner, one deployment. |
| Database | PostgreSQL with PostGIS | The data is relational and money related, and needs transactions, constraints and a spatial index. |
| Object storage | S3, with MinIO locally | The bucket is private, so every download is a five minute presigned link. |
| Frontend | React, TypeScript, Vite, TanStack Query | Server state in one place, types generated from the API contract rather than written by hand. |
| Jobs | A worker container polling Postgres | Four periodic jobs do not need a broker. |
| Contracts | `openapi-typescript`, a drift check in CI, and a fuzzer | The frontend cannot silently drift from the backend. |
| Deploy | One instance, Docker Compose, Caddy | Cheap, understandable, and it makes the whole path inspectable. |

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
  next phase and they are deliberately the next phase.
