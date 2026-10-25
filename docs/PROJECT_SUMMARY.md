# Smart Printing Network — one-page project summary

A web platform where a customer uploads a document, sees the price from a
nearby verified print shop, pays, and collects the order with a pickup
code. Shops work a queue of paid orders from a counter screen. Built as a
portfolio project to be **testable, deployable and explainable**, not as a
startup.

## By the numbers

Measured on 2026-10-25 unless stated otherwise. The latency figures are
from 2026-10-22. These are local or CI numbers, not production numbers,
and they are reported as measured.

| Fact | Value | How it was measured |
|---|---|---|
| Backend tests | **819 passed, 29 skipped** | `make coverage` (pytest) against real PostgreSQL 16 + PostGIS 3.6 |
| Frontend tests | **168 passed** in 27 files | `make test-fe` (Vitest + Testing Library) |
| Statement coverage | **91.7%** overall (4,867 / 5,307 lines) | `coverage.py`; floors are 80% overall |
| Business-logic coverage | **93.2%** domain, **92.4%** services | `scripts/check_coverage.py`; floors are 90% each |
| Architecture decision records | **34** | `docs/adr/`, indexed in `docs/DECISIONS.md` |
| CI wall time | **3m 53s**, six jobs, all green | GitHub Actions run `40171741317`; the dependency-audit steps were added after this run, so their cost is not in this figure |
| Container image build | **4m 16s** | Deploy run `40171741310`; the deploy job is opt-in (`DEPLOY_ENABLED`) and was skipped, so no production deploy time is claimed |
| Quote latency | p95 **25.4 / 25.8 ms** over two runs | k6 on 2026-10-22, 120 requests per run, local Compose stack |
| Shop search latency | p95 **137.2 / 133.1 ms** | k6 on 2026-10-22, 60 requests per run; spatial index in the plan |
| Vendor queue latency | p95 **61.0 / 28.4 ms** with **238 active orders** | k6 on 2026-10-22, 30 requests per run; partial index used |
| Failed requests | **0.00%** in both load runs | k6 `http_req_failed` |
| Wait-estimate accuracy | rule MAE **3.4140 min** vs **5.9899 min** for a global-average baseline | walk-forward backtest over 89 **simulated** orders; the simulation cannot justify ML |
| Security scans | no known vulnerable dependencies, no leaks | `pip-audit`, `npm audit` (0), `gitleaks` over 122 commits / 3.56 MB |

Latency was measured on an Apple Silicon laptop with PostGIS under Rosetta
emulation, so it is a regression baseline rather than a production claim.
The raw numbers and methodology are in
[`../perf/BASELINE.md`](../perf/BASELINE.md).

## Resume bullets

- Built a print-shop marketplace end to end: FastAPI, React, PostgreSQL
  with PostGIS, S3-compatible object storage, a background worker, and a
  single-origin Docker Compose deployment behind Caddy.
- Enforced the money path server-side: integer paise pricing in one pure
  module, a signed webhook verified on the raw body and deduplicated by
  event id, and a database `CHECK` on the stored amount.
- Kept state changes in one place: every order transition goes through
  `OrderService.transition()` and writes an audit event in the same
  transaction.
- Reached **91.7% statement coverage** with **819 backend tests** against
  a real PostgreSQL/PostGIS database, including authorization, forged
  webhook, duplicate delivery, and cross-tenant cases.
- Held **p95 under 26 ms** for quoting and **under 140 ms** for spatial
  shop search, with **0% failed requests** at 238 active orders in the
  queue.
- Shipped CI in **under four minutes** (3m53s before the audit steps were
  added) covering lint, strict typing, import contracts, backend, frontend,
  API contract, browser E2E and secret scanning, plus dependency audits in
  the backend and frontend jobs.
- Rejected ML for wait estimates after a leakage-free backtest: a simple
  rule beat a global-average baseline (**3.41 vs 5.99 min MAE**) on
  simulated data, so no model was added.

## What to inspect first

| Question | Where |
|---|---|
| How is the system put together? | [`README.md`](../README.md#architecture-at-a-glance) |
| Why these tools and not others? | [`docs/DECISIONS.md`](DECISIONS.md) |
| How is money and payment handled? | [`docs/adr/004-webhook-is-the-source-of-truth.md`](adr/004-webhook-is-the-source-of-truth.md) |
| What does the database enforce? | [`docs/adr/010-price-invariant-enforced-by-the-database.md`](adr/010-price-invariant-enforced-by-the-database.md) |
| How is security checked? | [`docs/SECURITY_REVIEW.md`](SECURITY_REVIEW.md) |
| What does it look like? | [`docs/DEMO.md`](DEMO.md), [`docs/screenshots/`](screenshots/) |

## Scope, stated plainly

Payments run in Razorpay test mode only; no real money moves, and vendor
payouts are out of scope. Search and estimates use seeded demo shops and
simulated history where the page says so. The project deliberately leaves
out delivery, notifications, admin UI beyond shop approval, QR codes and
ML; the README lists the exclusions, and the detailed phase plan is kept
on the development machine rather than published.
