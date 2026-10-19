# ADR 002: Sync SQLAlchemy and plain def endpoints

Date: 2026-10-19
Status: Accepted
Requirement: all Phase 1 backend work, BACKEND_STRUCTURE

## Context

The API is a single instance serving a modest workload: database reads and writes, plus calls to Razorpay and S3. Almost all request time is I/O waiting, and the only CPU-heavy work (PDF analysis) is routed to the worker. Async Python imposes real costs: async drivers, careful session handling, harder tests, and library edges everywhere.

## Decision

Use synchronous SQLAlchemy 2.0 with psycopg 3, and plain `def` FastAPI endpoints. FastAPI runs `def` endpoints in a thread pool, so requests still overlap. CPU-heavy work runs in the worker, never in the request path.

## Alternatives considered

1. **Async SQLAlchemy with asyncpg.** Rejected: measured concern is correctness and clarity at this scale, not raw concurrency; the complexity budget is better spent on tests, money handling and authorization. Also avoids mixing async sessions with sync boto3 and sync PyMuPDF.
2. **Django ORM.** Rejected with ADR 001.

## Consequences

- Thread pool size becomes a tuning knob under load; default executor settings are fine for a single instance and documented in ARCHITECTURE.
- No accidental blocking of the event loop by sync code inside async handlers, because there are no async handlers.
- Tests are straightforward: real Postgres, plain sessions, no async fixtures.
- On the deploy image, uvicorn runs without uvloop benefits; throughput headroom is far beyond current needs.

## Revisit trigger

When p95 latency is dominated by thread pool starvation on a multi-instance deployment, or a genuinely high-concurrency streaming path is required.
