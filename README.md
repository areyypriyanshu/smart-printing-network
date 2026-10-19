# Smart Printing Network

A web platform that connects customers with nearby verified print shops.
Upload a PDF, choose print options, see the price from the shop's own rate
card, pay, and collect your order with a short pickup code. Shops work a
queue of paid orders from a counter screen.

> **Status:** Phase 1 is built end to end. A customer can upload, get a
> price, pay, and collect. A shop can accept, print, mark ready and hand
> over against the pickup code. The worker expires unpaid orders, rejects
> orders no shop picked up, retries refunds and deletes old files.
> Payments run in Razorpay **test mode only**. No real money moves and shop
> payouts are out of scope.

Built by Priyanshu Mandal as a portfolio project with three goals:
**testable**, **deployable**, **explainable**.

[![CI](https://github.com/areyypriyanshu/smart-printing-network/actions/workflows/ci.yml/badge.svg)](https://github.com/areyypriyanshu/smart-printing-network/actions/workflows/ci.yml)
[![Backend tests](https://github.com/areyypriyanshu/smart-printing-network/actions/workflows/ci.yml/badge.svg?branch=main&job=backend)](https://github.com/areyypriyanshu/smart-printing-network/actions/workflows/ci.yml)

---

## What it does, by phase

| Phase | Scope | Status |
|---|---|---|
| 1 | Accounts and roles, PDF upload and validation, print options, server-side pricing, payment and signed webhooks, pickup code, vendor queue, refunds, timeouts, file retention. Pickup only. | **Built** |
| 2 | PDF quality checker (effective DPI and blur), geo search of shops, price comparison, map view | Planned |
| 3 | Live queue and wait estimates from real order history, WebSocket updates, estimate accuracy report. ML only if the data justifies it. | Planned |

## What it deliberately does not do

- No delivery, no delivery tracking, no route optimisation (OR-Tools). Pickup only.
- No CNN or deep learning. Blur and resolution checks use classical image analysis because it is enough and it is explainable.
- No "AI price prediction". Price is arithmetic: `pages x copies x shop rate`, with a minimum order amount.
- No vendor payouts or settlements, no GST invoicing, no email or SMS notifications, no admin UI.

## Architecture at a glance

```mermaid
flowchart LR
  B[Browser: React SPA] -->|HTTPS| C[Caddy]
  C -->|/api| A[FastAPI API]
  C -->|static files| F[Built frontend]
  A --> D[(PostgreSQL + PostGIS)]
  A --> S[(S3 / MinIO)]
  A -->|create order, refund| R[Razorpay]
  R -->|signed webhooks| C
  W[Worker: scheduled jobs] --> D
  W --> S
  W -->|refunds| R
```

One origin, one TLS terminator, no CORS, and the refresh cookie is always
first party.

## Tech stack

- **Frontend:** React 19, TypeScript, Vite, TanStack Query, React Hook Form, Zod, Tailwind CSS
- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Pydantic v2
- **Data:** PostgreSQL with PostGIS, S3-compatible object storage (MinIO locally)
- **PDF and images (Phase 2):** PyMuPDF, OpenCV
- **Payments:** Razorpay (test mode) behind a gateway interface, with a fake gateway for tests
- **Infra:** Docker Compose, Caddy, GitHub Actions, single instance with S3

## Quickstart

Prerequisites: Git, Docker Desktop (Windows or macOS) or Docker Engine
(Linux), and `make`. On Windows, use WSL2 for `make`, or run the
underlying commands from the `Makefile` directly.

For the fast, native checks (`make check`, `make test-fe`) you also need
[uv](https://docs.astral.sh/uv/) and Node 22 (`frontend/.nvmrc`), then
`uv sync` in `backend/` and `npm ci` in `frontend/`.

```bash
git clone https://github.com/areyypriyanshu/smart-printing-network.git
cd smart-printing-network
cp .env.example .env      # local defaults, PAYMENT_PROVIDER=fake
make up                   # builds and starts api, worker, db, minio, frontend
make migrate              # applies database migrations
make seed                 # three verified shops, one customer
```

The PostGIS image is published for amd64 only, so `docker-compose.yml`
pins the `db` service to `linux/amd64`; on Apple Silicon Docker Desktop
runs it through Rosetta emulation automatically. `make up` copies
`.env.example` to `.env` if missing.

| What | URL |
|---|---|
| App | http://localhost:5173 |
| API docs (OpenAPI) | http://localhost:8000/docs |
| MinIO console | http://localhost:9001 |

Demo accounts, created by `make seed` (local and CI only, never production):

| Role | Email | Password |
|---|---|---|
| Customer | customer@example.com | spn-demo-password |
| Vendor (shop 1) | vendor1@example.com | spn-demo-password |
| Vendor (shop 2) | vendor2@example.com | spn-demo-password |
| Vendor (shop 3) | vendor3@example.com | spn-demo-password |

Seeded shops are verified and accepting orders. A vendor that
self-registers through the app starts unverified; approve it locally with
`docker compose run --rm api python -m app.cli verify-shop <vendor-email>`.

### The same stack with HTTPS, the way it is deployed

The production Compose file runs locally too, so the whole path can be
exercised before there is a domain:

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml run --rm api alembic upgrade head
docker compose -f docker-compose.prod.yml exec -T api python -m app.cli seed
```

Caddy issues a certificate from its own local authority, so the browser
warns once. To trust it:

```bash
docker compose -f docker-compose.prod.yml exec -T caddy \
  cat /data/caddy/pki/authorities/local/root.crt > caddy-ca.crt
sudo security add-trusted-cert -d -k /Library/Keychains/System.keychain caddy-ca.crt
```

Then the app is on <https://localhost>.

## Try the whole flow in one command

`infra/scripts/smoke-test.sh` walks the product the way a person would:
the customer signs in, uploads a PDF, sees a price, pays; the shop finds
the order in the queue, accepts it, starts printing, marks it ready; the
customer downloads the file; a wrong pickup code is refused; the right one
completes the order.

```bash
make smoke                                   # against the dev stack
BASE_URL=https://localhost CURL_CA_BUNDLE=./caddy-ca.crt infra/scripts/smoke-test.sh
```

It checks the answer at every step, so it fails loudly rather than
printing a summary that looks fine.

## Common commands

| Command | What it does |
|---|---|
| `make check` | Lint, type check, import contracts and all fast tests. Run before every commit. |
| `make test-unit` | Pure domain tests (pricing, state machine, backoff). Milliseconds. |
| `make test-api` | API and integration tests against a real Postgres. |
| `make test-jobs` | Background job tests with a frozen clock. |
| `make test-fe` | Frontend component tests (Vitest). |
| `make coverage` | The whole suite with coverage, then the coverage floors. |
| `make e2e` | Playwright journeys and accessibility checks against the full stack. |
| `make smoke` | The end to end product flow against a running stack. |
| `make openapi` | Exports `backend/openapi.json` and regenerates `frontend/src/api/schema.d.ts`. |
| `make reset` | Wipes local volumes and rebuilds from scratch. |

## Testing

- **Unit:** the pricing rule, the order state machine and the refund
  backoff, including property-based tests with Hypothesis.
- **API and integration:** real PostgreSQL with PostGIS, the fake payment
  gateway and in-memory storage. Covers webhook replay, parallel webhook
  delivery, concurrent accept, authorization on every endpoint, and the
  background jobs.
- **End to end:** Playwright against the whole Compose stack, plus axe
  accessibility checks at WCAG 2.1 A and AA.
- **Contract:** Schemathesis fuzzes the API from its own OpenAPI schema,
  with a token so the authenticated endpoints are reached too. It found a
  real bug: registering a shop with an email that already existed returned
  a 500 instead of a 409.
- **Coverage floors**, enforced in CI: 90% on `domain`, 90% on `services`,
  80% overall. Currently 100%, 93% and 92%.
- **CI:** six jobs, backend, frontend, contract, end to end, OpenAPI drift
  and a secret scan.

## Deploying

The production stack is `docker-compose.prod.yml` with Caddy in front. It
runs locally, which is the fastest way to see the whole thing.

For a real deployment, push to `main` and the deploy workflow builds the
image, runs the migrations as a one-off container, deploys, smoke checks
`/readyz`, and rolls back to the previous image tag if the check fails.

The deploy job is skipped until a target is configured. To set one up:

1. An AWS instance with Docker, a domain pointing at it, and ports 80 and
   443 open.
2. Repository secrets: `DEPLOY_HOST`, `DEPLOY_SSH_KEY`, `POSTGRES_PASSWORD`,
   `S3_SECRET_KEY`. A repository variable `DEPLOY_ENABLED` set to `true`.
3. An environment variable `SPN_DOMAIN` on the `production` environment.
4. `ACME_EMAIL` in the instance's `.env`, so Caddy can register the ACME
   account.

The migrations are backward compatible with the previous version, so a
rollback is a redeploy of the previous tag.

## Documentation

The planning documents live on the maintainer's machine and are not
committed. The decisions are.

| Doc | Purpose |
|---|---|
| [`AGENTS.md`](AGENTS.md) | Rules and workflow for AI agents and contributors |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | **Start here.** Why the project is built the way it is |
| [`docs/adr/`](docs/adr/) | One architecture decision record per decision |

## Engineering decisions worth reading

1. **The webhook, not the browser, decides that an order is paid.** The
   signature is checked on the raw bytes, the event id deduplicates, and
   the amount and currency must match. A late payment is refunded.
2. **One function changes an order's status**, and it does a compare and
   swap, so two shops clicking Accept at once produce one winner. The
   status change and its history row commit together.
3. **The database checks the price.** `price_paise = GREATEST(page_count
   x copies x rate_paise, min_order_paise)` is a constraint, so a bug in
   the application cannot store a wrong price.
4. **The domain layer is pure**, and an import linter contract fails the
   build if it ever imports a framework.
5. **The payment provider sits behind an interface** with a real fake, so
   the whole money path runs the same way in the tests, locally and in
   the demo.
6. **Background work is database driven**, with no Redis and no Celery.
   Four functions, rows claimed with `SKIP LOCKED`, safe to run twice.

## Known limitations

- Payments are test mode. Vendor payouts are not implemented.
- One shop per vendor account, one order per upload, whole-document printing only (no page ranges, no binding options).
- No email verification or password reset.
- Single-instance deployment. The rate limiter lives in the process, so a
  second API instance would need Redis.
- The vendor board polls every five seconds. WebSockets arrive in the
  phase where a live board needs them.

## Author

Priyanshu Mandal, final-year B.Tech Information Technology.
GitHub: [areyypriyanshu](https://github.com/areyypriyanshu) | LinkedIn: [areyypriyanshu](https://linkedin.com/in/areyypriyanshu)
