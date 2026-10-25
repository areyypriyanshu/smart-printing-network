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

## The six decisions that shape everything else

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

`app/domain/` is ten small modules with no imports outside the standard
library. An import linter contract fails the build if it ever imports
SQLAlchemy, FastAPI, Pydantic or anything from the rest of the app. The
pricing rule, the state machine and the refund backoff schedule are
therefore testable without a database, an event loop or a mock.
[ADR 001](adr/001-fastapi-over-node-express.md),
[ADR 002](adr/002-sync-sqlalchemy-plain-def-endpoints.md)

### 4. The payment provider sits behind an interface, with a real fake

`PaymentGateway` is a `Protocol`. `RazorpayGateway` uses `urllib` from
the standard library rather than adding a dependency, and `FakeGateway`
signs real HMAC webhooks. The whole test suite and the local stack run
against the fake, so the money path is exercised the same way in every
environment.
[ADR 009](adr/009-payment-gateway-interface.md),
[ADR 010](adr/010-price-invariant-enforced-by-the-database.md)

### 5. Background work is database driven, with no broker

Expiring unpaid orders, rejecting orders no shop picked up, expiring
no-shows, retrying refunds, deleting old files and analysing uploaded
files for quality are six functions that query Postgres,
claim rows with `FOR UPDATE SKIP LOCKED`, and update them conditionally.
There is no Redis, no Celery and no separate queue to run, monitor or
debug. A second worker is safe by construction.
[ADR 003](adr/003-database-driven-jobs.md),
[ADR 008](adr/008-single-instance-docker-compose.md)

### 6. Clerk proves who someone is, this database decides what they may do

Sign-up, sign-in, passwords, the verification email, sessions and
social sign-in are Clerk's. The role, the shop, the order, the money,
the file and **every ownership check** stay here, in the services,
where a missing router check cannot leak anything. The role is read
from the database row, never from the token, and a cross-tenant
request is still a 404.

The local account is created exactly once, by the import for an
existing person or by an explicit onboarding step for a new one, and
the role is chosen there and never changes. A webhook keeps the local
copy in step, and it can only do a closed list of things: it cannot
write a role.

This reverses an earlier decision, and the reversal is written down
rather than slipped in. The previous version rejected third-party
providers because they "hide the thing being demonstrated"; the
authentication was the interesting part then, and the ownership rules
are what is interesting now. The cost is named too: on the free tier
the verification email and the sign-in screen carry Clerk's branding
and cannot be edited.
[ADR 029](adr/029-clerk-authentication-with-local-authorization.md)

---

## What was deliberately left out

The original idea promised more than is sensible to build, and the
decisions that keep this project honest are mostly about what not to
build.

| Left out | Why |
|---|---|
| Delivery, couriers, route optimisation | Needs live location and failure handling. Pickup only. |
| A CNN for blur detection | No labelled dataset and no evaluation. Effective DPI plus Laplacian variance on a labelled fixture set answers the same question and can be explained. |
| Machine learning for price or wait estimates | Price is arithmetic. Wait estimates use recent speed quartiles and current unfinished work. ML is rejected unless a candidate beats that rule on time-separated real data; simulated history cannot justify it. See [ADR 033](adr/033-wait-estimates-and-the-ml-decision.md). |
| Vendor payouts, GST invoicing | Marketplace money movement needs KYC, split payments and legal review. |
| Email and SMS notifications | In app status only, for now. Clerk sends the one message that proves an address; the `EmailSender` interface is kept for the product email that this backlog will need, and Brevo plugs into it without code. |
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
one address. The end-to-end suite found this by tripping it. The
endpoint this protected is Clerk's after the migration, and the
provider does the limiting; the rule is kept here because the same
shape is needed for the endpoints that are still ours.
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
The hashing is Clerk's after the migration, so the CPU argument goes
with it, but the rule survives in a new form: the endpoints that are
still ours, such as the public webhook and the onboarding step, are
limited for the same reason, because an anonymous caller must not be
able to make the server do unbounded work.
[ADR 025](adr/025-the-limits-on-creating-an-account.md)

**An email address is a claim until it is proved.** A link is sent to
the address, and opening it proves it. The account works while it is
unproved, but it cannot order a print, because the printout and the
pickup code are tied to the address. A customer who typed the address
wrong can put the right one there, which is the only way out of a
mistyped address. The claim is still a claim and the rule is still the
rule; after the migration Clerk sends the link and proves the address,
and **this application keeps no copy of the answer and asks nothing**.
The provider does not let anybody sign in until the address is proved,
so a copy here could only ever disagree with the truth, and it
disagreed in the way that costs a customer.
[ADR 026](adr/026-the-email-address-has-to-be-proved.md),
[ADR 029](adr/029-clerk-authentication-with-local-authorization.md)

**A provider never takes over an account here.** The rule outlived the
hand written OAuth client that first carried it, and it outlives that
client's removal: the local account is keyed on the identity provider's
subject and never on the email address. Clerk links accounts inside its
own store by email, and that does not change the subject, so a provider
cannot take over a local account here.
[ADR 027](adr/027-sign-in-with-google-without-a-new-dependency.md),
[ADR 029](adr/029-clerk-authentication-with-local-authorization.md)

**The content security policy allows the provider's fraud
protection to run.** It is a widget from Cloudflare, it runs in the
page, and it does two things the policy has to allow: it evaluates the
code it is given, and it fetches an empty address to see whether the
page is allowed to fetch at all. Without them the widget cannot start,
the check it exists for never finishes, and nobody can create an
account. The empty address reaches no host.
[ADR 029](adr/029-clerk-authentication-with-local-authorization.md)

**The verification email is Clerk's, and the product email is
Brevo's.** A verification link, a magic link and a password reset all
carry a token only the identity provider can validate, so they have to
come from Clerk, and Clerk cannot be pointed at a different mail
server. An order receipt or a campaign carries no such token, so it
belongs to the application, and it goes out through the `EmailSender`
interface and SMTP. The application keeps that interface, which is
already a protocol with a test double, and Brevo plugs into it with no
code at all.
[ADR 029](adr/029-clerk-authentication-with-local-authorization.md)

**The quality check is measured, and it never blocks an order.** The
analysis runs in the worker on a file that came from a stranger, so it is
bounded on every axis: pages, pictures on a page, the size of every
rendered region and the time the file may take. A file that breaks a
bound gives a failed report, not a hung worker. The thresholds are not
folklore: they are chosen on the calibration half of a labelled fixture
set and reported on the half that was held out, and the evaluation is in
the repository. The report is advisory, so acknowledging it is a fact
about the customer rather than a permission the server asks for.
[ADR 028](adr/028-the-quality-check-runs-in-the-worker.md)

[ADR 016](adr/016-office-file-upload.md) has the full reasoning for the
conversion, including the alternatives that were rejected and why.

---

## The shop the customer finds

A customer wants a print shop near them and the price for their job.
The price is the interesting part, because there is only one honest way
to show it: the search and the checkout call the same pricing function,
so the number the customer compares is the number the customer is
charged. A test creates a real order through the real service and
compares the two numbers, because two pieces of arithmetic that agree
today drift apart by next month.

The distance is measured by the database, on the geography column, with
`ST_DWithin`, so the index is used and a shop outside the radius is not
in the answer at all. The radius is in metres, and a test puts a shop a
thousandth of a degree north of the customer and asks for about a
hundred and eleven metres, which catches the latitude and longitude
being swapped.

**A shop that cannot do the job is not in the comparison.** When prices
are asked for, the rate for the chosen options is joined into the query,
so a shop without that rate is absent rather than present with a price
nobody can pay.

**The address is looked up on the server, and the shop owner's own
coordinates win.** A shop owner who typed a latitude and a longitude is
believed, because they know where their own shop is better than a map
does, and a map will put a shop in the middle of a lake because the
address on the letter is short. Only when there are no coordinates is
the address looked up, and the lookup happens on this server, so the map
provider's key never reaches the browser. A deployment without a provider
still works: the owner types the coordinates, and a customer who cannot
share a location sees the whole list.
[ADR 030](adr/030-the-address-is-looked-up-on-the-server.md)

**The free provider is the default, and the rules it asks for are code.**
OpenStreetMap's geocoder needs no key, no account and no bill, and it
is run on donated servers. Its policy asks for four things, and each one
is a test rather than a habit: one call a second for the whole
application, a user agent that says who is asking, the answers cached,
and the attribution shown wherever the data is shown. The commercial
provider is one setting away, and so is having no provider at all.
[ADR 031](adr/031-the-free-geocoder-and-the-rules-that-come-with-it.md)

**The map is drawn last, and the list is the map that always works.**
The customer's map is the provider's script, loaded when the customer
scrolls to it, not when the page opens. The key is public and is made
safe by the restriction in the provider's console, not by secrecy. A
deployment with no key, a blocked script or a screen reader still has
the list, with the same shops, the same distances and the same prices,
and the map never becomes the only way to reach a shop. See
[ADR 032](adr/032-the-map-is-drawn-last.md).

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
| The quality rules find the bad pages | The labelled fixture set is measured, and the test asserts the targets on the half that was held out: at least 90% of the bad pages flagged, at most 10% of the good ones. |
| A quality warning never blocks an order | An order is placed with the warnings unacknowledged, and with them acknowledged, and both go through. |
| A quality report belongs to one customer | Another customer's report is 404, not 403, so the answer never confirms that it exists. |
| The price on the shop search is the price of the order | A real order is created through the real service and its price is compared with the price the search showed. |
| The place on the map is the place | A shop a thousandth of a degree north of the customer has to be about a hundred and eleven metres away, which fails if the latitude and the longitude are swapped. |
| The free map provider is used within its rules | One call a second for the whole application, a user agent that names the application, the answers cached, and the attribution shown on the page. Each one has a test, and a test that would still pass if the rule were broken does not count. |
| One shop's rate cannot break the search for everybody | The rate of a page has a ceiling, refused at the door on both sides of it, and the arithmetic that decides the order of the shops multiplies three 32 bit integers cast to 64 bit ones first. The test asks for the price of a shop with an absurd rate, and the search still answers. |
| A rate that was stored before the ceiling existed is still readable | Reading a rate is not the same model as setting one. A shop with a strange rate must not make the page that lists the shops fail to load for everybody. |

---

## All decision records

Every decision has its own file, with the context, the alternatives that
were rejected, the consequences and the trigger for revisiting it.

| ADR | Decision |
|---|---|
| 001 | [ADR 001: FastAPI over Node/Express](adr/001-fastapi-over-node-express.md) |
| 002 | [ADR 002: Sync SQLAlchemy and plain def endpoints](adr/002-sync-sqlalchemy-plain-def-endpoints.md) |
| 003 | [ADR 003: Database-driven jobs, no Redis or Celery](adr/003-database-driven-jobs.md) |
| 004 | [ADR 004: The signed webhook, not the browser, decides that an order is paid](adr/004-webhook-is-the-source-of-truth.md) |
| 005 | [ADR 005: Text columns with CHECK constraints instead of Postgres enums](adr/005-text-and-check-constraints.md) |
| 006 | [ADR 006: Classical image analysis instead of a neural network](adr/006-classical-image-analysis-not-a-cnn.md) |
| 007 | [ADR 007: Polling first, WebSockets in Phase 3](adr/007-polling-before-websockets.md) |
| 008 | [ADR 008: Single instance with Docker Compose before managed AWS services](adr/008-single-instance-docker-compose.md) |
| 009 | [ADR 009: A payment gateway interface with a fake implementation](adr/009-payment-gateway-interface.md) |
| 010 | [ADR 010: The price rule is enforced by a database constraint](adr/010-price-invariant-enforced-by-the-database.md) |
| 011 | [ADR 011: Community-built MinIO image for local object storage](adr/011-community-minio-image.md) |
| 012 | [ADR 012: In-memory sliding window rate limiter instead of slowapi](adr/012-in-memory-rate-limiter.md) |
| 013 | [ADR 013: Cash on collection, as a second payment method](adr/013-cash-on-collection.md) |
| 014 | [ADR 014: A narrow admin panel, not a general one](adr/014-admin-panel.md) |
| 015 | [ADR 015: A database browser in the local stack](adr/015-database-browser-for-local-development.md) |
| 016 | [ADR 016: Printing the file the student actually has](adr/016-office-file-upload.md) |
| 017 | [ADR 017: Printing it again copies the file, it does not share it](adr/017-print-it-again.md) |
| 018 | [ADR 018: Sharing the pickup code, and who that trusts](adr/018-sharing-the-pickup-code.md) |
| 019 | [ADR 019: Rate limiting a login per account and per address](adr/019-rate-limiting-a-login-per-account.md) |
| 020 | [ADR 020: One style per role, written down once](adr/020-one-style-per-role.md) |
| 021 | [ADR 021: The dialogs use the native `dialog` element, not Radix](adr/021-native-dialog-element.md) |
| 022 | [ADR 022: The webhook event and the payment it causes are one transaction](adr/022-the-webhook-event-and-its-effect-are-one-transaction.md) |
| 023 | [ADR 023: The deployment runs the commit it reviewed, in a mode it pins](adr/023-the-deployment-runs-the-commit-it-reviewed.md) |
| 024 | [ADR 024: The boundary refuses a value the database cannot hold](adr/024-the-boundary-refuses-a-value-the-database-cannot-hold.md) |
| 025 | [ADR 025: The limits on creating an account](adr/025-the-limits-on-creating-an-account.md) |
| 026 | [ADR 026: The email address has to be proved](adr/026-the-email-address-has-to-be-proved.md) |
| 027 | [ADR 027: Sign in with Google, without a new dependency](adr/027-sign-in-with-google-without-a-new-dependency.md) |
| 028 | [ADR 028: The quality check runs in the worker, on a labelled fixture set](adr/028-the-quality-check-runs-in-the-worker.md) |
| 029 | [ADR 029: Clerk proves who someone is, this database decides what they may do](adr/029-clerk-authentication-with-local-authorization.md) |
| 030 | [ADR 030: The address is looked up on the server, and the shop owner's own coordinates win](adr/030-the-address-is-looked-up-on-the-server.md) |
| 031 | [ADR 031: The free geocoder is the default, and the rules that come with it](adr/031-the-free-geocoder-and-the-rules-that-come-with-it.md) |
| 032 | [ADR 032: The map is drawn last, and the list is the map that always works](adr/032-the-map-is-drawn-last.md) |
| 033 | [ADR 033: Queue-wait estimates stay rule-based; simulated data cannot justify ML](adr/033-wait-estimates-and-the-ml-decision.md) |
| 034 | [ADR 034: Live updates over an authorized WebSocket, with polling as the fallback](adr/034-websocket-live-updates.md) |

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
- The vendor board has a WebSocket, with polling every five seconds as
  the fallback when the socket drops. The socket is a notification, not
  the source of truth: every message makes the client resync from the
  API, and authorization is decided on the server. See
  [ADR 034](adr/034-websocket-live-updates.md).
- The PDF quality checker and the map view are built. The checker
  measures the file on a labelled set and only advises. The map is an
  addition to the list: it is loaded when the customer scrolls to it,
  and the list of shops near the customer, with their prices, is still
  the way to compare and order when the map is missing.
- A converted Word, Excel or PowerPoint file keeps the text, the
  headings, the pictures and the table contents. It does not keep the
  fonts, the exact table widths, the headers, the footers or the
  columns. A student who needs the exact layout uploads a PDF.
