# ADR 012: In-memory sliding window rate limiter instead of slowapi

Status: accepted (Sprint 1)

## Context

Auth endpoints can be brute forced: login (password guessing), register and register-vendor (spam accounts). Sprint 1 needs a rate limit on these endpoints. `TECH_STACK.md` originally listed slowapi. The deployment is one API instance; the documented trigger for Redis is not reached yet (TECH_STACK "Revisit if"). `AGENTS.md` notes that in-memory rate limiting silently breaks with a second API instance; this is a documented limitation of the single-instance design, not something to patch locally.

## Decision

Ship `app/rate_limit.py`: a small sliding window limiter keyed by client IP, exposed as a FastAPI dependency factory (`rate_limit(limit, window_seconds, scope)`). The limiter instance lives on `app.state.rate_limiter`, so each app (including tests) gets a fresh one. Exceeding the limit raises `RateLimited` (429) with a `Retry-After` header. Unit tested with a fake clock (`tests/unit/test_rate_limit.py`).

## Rejected alternatives

- **slowapi**: adds a dependency plus the `limits` package for a rule we can express in about 40 lines; its decorator style also cuts across the FastAPI dependency injection the routers already use for auth. Nothing in slowapi is hard to replace later.
- **Fixed window counter**: a burst can pass at a window boundary (2x limit across the edge). Sliding window of timestamp deque is barely more code.
- **Database-backed counting**: writes on every request for a rate limiter are wasteful at this scale and add cleanup work.

## Consequences

- Single instance only. When the API runs more than one instance, move counters to Redis (already the documented trigger) or accept keying by instance.
- Counters are per process and reset on restart. Acceptable for brute-force smoothing, not a security boundary.
- Keying uses `request.client.host`; behind a proxy the proxy address must be trusted (`--proxy-headers`) so the real client IP is used. Caddy and the compose setup are adjusted when production deploys are finalised (Sprint 5 hardening).
