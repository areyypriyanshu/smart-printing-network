# ADR 003: Database-driven jobs, no Redis or Celery

Date: 2026-10-19
Status: Accepted
Requirement: order expiry, auto-reject, refund retries, file purge, BACKEND_STRUCTURE section 7

## Context

The background work is small and stateful in Postgres already: expire unpaid orders, auto-reject unaccepted ones, retry refunds, purge expired uploads, and later claim quality-analysis rows. Volumes are low (hundreds of orders a day at most). Correctness requirements are high: jobs must be idempotent and safe to run twice or concurrently.

## Decision

Run a single worker container (`python -m app.jobs.scheduler`) that polls Postgres on an interval. Jobs are plain functions; concurrency safety uses `SELECT ... FOR UPDATE SKIP LOCKED` and conditional updates, so adding a second worker later is safe by construction. The worker touches a heartbeat file that the container healthcheck watches.

## Alternatives considered

1. **Celery with Redis.** Rejected: a broker, a result backend and a second state system to operate, for jobs whose real state already lives in Postgres. At this scale the broker adds failure modes without removing work.
2. **RQ with Redis.** Lighter, but still a broker with the same objection at the size of this workload.
3. **APScheduler inside the API process.** Rejected: couples job execution to the API lifecycle; a redeploy mid-job or a second API instance duplicates work with no coordination.

## Consequences

- No extra infrastructure. The Compose stack stays small; production deploys one more container.
- Polling cost is negligible at the expected volume; intervals are one minute for order jobs.
- Postgres becomes the queue. Fine here; it would not be the choice for high fan-out or long retry pipelines.

## Revisit trigger

Documented in ARCHITECTURE failure table: jobs need long retries, fan-out or visibility, or job load competes with request traffic. The named target is Redis with RQ or arq.
