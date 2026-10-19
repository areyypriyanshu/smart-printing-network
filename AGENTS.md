# AGENTS.md

Operating manual for AI coding agents and human contributors working on **Smart Printing Network (SPN)**. Read this fully before changing anything. When this file and the code disagree, say so and propose a fix to whichever is wrong. Do not silently pick one.

---

## 1. Mission and quality bar

SPN lets customers upload a PDF, choose print options, see a price, pay, and collect from a nearby verified print shop with a pickup code. Shops run an order queue from a vendor dashboard.

This repository is also the owner's main portfolio project (Priyanshu Mandal, final-year B.Tech IT student, targeting QA, DevOps and software roles). Therefore every change must be:

1. **Testable:** proven by automated tests at the right level.
2. **Deployable:** works in the Docker Compose stack and in CI, with safe migrations.
3. **Explainable:** a reviewer, or an interviewer, can understand why it was built this way. Non-trivial decisions get an ADR in `docs/adr/`.

Prefer boring, simple, correct code over clever code. A smaller change that is fully verified beats a bigger one that is probably fine.

## 2. Read first

| Need | Read |
|---|---|
| What and why, requirement IDs, scope | `docs/PRD.md` |
| Screens, order lifecycle, failure paths | `docs/APP_FLOW.md` |
| Why each tool was chosen or rejected | `docs/TECH_STACK.md` |
| Backend layers, endpoints, jobs, errors | `docs/BACKEND_STRUCTURE.md` |
| Tables, constraints, migrations policy | `docs/DATABASE_SCHEMA.md` |
| Entities and invariants (I1 to I14) | `docs/DATA_MODEL.md` |
| System design and failure modes | `docs/ARCHITECTURE.md` |
| Frontend conventions | `docs/FRONTEND_GUIDELINES.md` |
| Sprint order, phase gates, scope guard | `docs/IMPLEMENTATION_PLAN.md` |

Before starting a task, identify the requirement ID (for example FR-8) and the sprint it belongs to. If you cannot, the task may be out of scope.

## 3. Non-negotiable rules

Violating any of these is a defect, even if tests pass.

1. **Money is integer paise.** Never float, never decimal rupees. Price is computed only by `domain/pricing.py` on the server. The client never sends a price as truth.
2. **Only `OrderService.transition()` changes `orders.status`.** Never assign status anywhere else. Each transition writes its `order_events` row in the same transaction.
3. **The signed webhook decides that an order is paid.** Client callbacks and redirects never mark anything paid.
4. **Webhook handling:** verify the signature on the raw body, deduplicate by event id, check amount and currency, be idempotent, and return 5xx on transient failure so the provider retries.
5. **Authorization is object-level and lives in services.** Customers see only their own orders and uploads. Vendors see only their own shop's orders. Cross-tenant access returns 404. A new endpoint without an authorization test is not done.
6. **PDFs are private.** Private bucket, random storage keys, presigned URLs valid 5 minutes, retention rules enforced by `delete_after`. Never log PDF content or filenames beyond what is needed.
7. **No secrets in code, logs, tests, fixtures, or screenshots.** `.env.example` holds placeholders only. Never commit `.env`.
8. **Schema changes only through Alembic migrations.** Never edit a merged migration. Migrations must be backward compatible with the previous app version (expand and contract) and pass the up, down, up check.
9. **`domain/` is pure.** Standard library only, no I/O, no framework imports. import-linter enforces it.
10. **Phase discipline.** Do not build Phase N+1 features while the Phase N gate is open. The parking lot in `IMPLEMENTATION_PLAN.md` is binding.
11. **No fake intelligence.** No model, score, or "AI" label without data, a baseline and an evaluation. Rule-based first. State plainly when something is a simple rule.
12. **Tests are the spec.** Never weaken, skip, delete or loosen a failing test to get green. Fix the code, or explain why the test is wrong and change it in the open.
13. **Never invent.** Do not invent API methods, library options, endpoints, environment variables, or table columns. Check the docs, the code, or the library documentation. If unsure, say so.

## 4. Scope

**In scope by phase** (details in the PRD):
- **Phase 1:** accounts and roles, vendor rates, PDF upload and validation, pricing and quote, order and payment, pickup code, vendor queue, refunds and timeouts, file retention.
- **Phase 2:** PDF quality checker (effective DPI and blur), geo search, price comparison, map.
- **Phase 3:** wait estimates from real order events, WebSocket live updates, accuracy report.

**Out of scope (do not build, do not scaffold, do not add dependencies for):**
delivery and delivery tracking, OR-Tools routing, CNN or deep learning, ML price or ETA prediction, vendor payouts, GST invoicing, email or SMS notifications, admin UI, page ranges, binding, multi-file orders, QR codes, ratings, password reset, Kubernetes, Redis or Celery (until the documented trigger is reached).

If a request seems to require something out of scope, stop and ask before proceeding.

## 5. Repository layout

```
smart-printing-network/
  AGENTS.md  README.md  Makefile  .env.example  .gitattributes  .editorconfig
  docker-compose.yml  docker-compose.prod.yml
  docs/                  # PRD, APP_FLOW, TECH_STACK, ... and adr/
  backend/
    pyproject.toml  uv.lock  alembic.ini
    migrations/versions/
    app/
      main.py config.py db.py deps.py errors.py logging.py cli.py
      domain/            # pure rules: pricing, order_state, pickup_code, (P2) pdf_rules, (P3) estimates
      models/  schemas/  services/  routers/
      gateways/{payments,storage}/
      jobs/              # scheduler and job modules
      quality/           # (P2) analyzer
    tests/{unit,integration,api,jobs,fixtures}
  frontend/
    src/{api,features,components/ui,lib,test}
  e2e/                   # Playwright
  infra/                 # Caddyfile, scripts (backup, restore drill, deploy)
  .github/workflows/     # ci.yml, deploy.yml
```

Layering: `routers -> services -> models`, with `services -> domain` and `services -> gateways (interfaces)`. Routers contain no business logic. Services own transactions. See `BACKEND_STRUCTURE.md`.

## 6. Commands

Run from the repository root. On Windows without `make`, use WSL2 or run the underlying commands from the `Makefile`.

| Command | Purpose |
|---|---|
| `make up` / `make down` | Start or stop the Compose stack |
| `make migrate` | Apply Alembic migrations |
| `make seed` | Demo shops, rates, customer |
| `make check` | Lint, types, import-linter, fast tests. **Run before declaring anything done.** |
| `make test-unit` | Domain tests |
| `make test-api` | API and integration tests with real Postgres |
| `make test-fe` | Frontend component tests |
| `make e2e` | Playwright against the full stack |
| `make openapi` | Export OpenAPI and regenerate frontend types |
| `make reset` | Wipe local volumes and rebuild |

If a command does not exist yet or fails for an unrelated reason, report it. Do not work around it silently.

## 7. Conventions

### Python
- Python 3.12. Type hints everywhere. `mypy` strict on `domain/` and `services/`. `ruff` for lint and format.
- Plain `def` endpoints and services (sync SQLAlchemy). CPU-heavy work goes to the worker.
- Raise typed `AppError` subclasses. No bare `except`. No `print`. Use the logger.
- Pydantic models for all request and response bodies. Never return ORM objects directly.
- Time: timezone-aware UTC. Inject clocks or use freezable time in jobs. No naive datetimes.
- IDs are UUIDs. Never expose sequential database ids. `order_no` is the human-friendly number.

### API
- Base path `/api/v1`. Error body `{ "error": { "code", "message", "details" } }`. Codes listed in `BACKEND_STRUCTURE.md`. Add new codes there in the same change.
- `POST /orders` requires `Idempotency-Key`.
- Pagination by cursor. No unbounded list endpoints.

### SQL and migrations
- `snake_case`, plural tables, `_paise` suffix for money, `timestamptz` for time, `text` plus `CHECK` instead of enums.
- Every foreign key declared. Add indexes for real query patterns, with a reason in the PR.
- One logical change per migration, reversible unless explicitly stated.

### TypeScript and React
- `strict` TypeScript, no `any`. Server state in TanStack Query, forms with React Hook Form and Zod. API types generated from OpenAPI. Rules in `FRONTEND_GUIDELINES.md`.
- Every screen has loading, empty and error states. Status is never conveyed by colour alone.

### Git
- Short-lived branches from `main`. Conventional Commits: `feat(orders): ...`, `fix(webhooks): ...`, `test(...)`, `docs(...)`, `chore(...)`, `refactor(...)`.
- Small pull requests (aim under about 400 changed lines). Description answers: what changed, why (requirement ID), how it was tested, risks, and anything not verified.
- Never force-push to `main`. Never commit generated secrets or large binaries.

### Dependencies
- Prefer the standard library and existing dependencies. A new dependency needs a one-paragraph justification in the PR (what it replaces, maintenance status, licence). Add an ADR if it changes the stack.

## 8. Testing policy

Test at the lowest level that can prove the behaviour.

| Change type | Required tests |
|---|---|
| Domain rule (pricing, transitions, estimates) | Unit tests plus a Hypothesis property where a property exists |
| Service behaviour with database effects | Integration test against real PostgreSQL with PostGIS |
| New or changed endpoint | API test for success, validation errors, authentication, and **authorization (allowed and forbidden actor)** |
| Webhook or payment code | Forged signature, duplicate delivery, wrong amount, late payment, parallel delivery |
| Background job | Frozen-time test, idempotency (run twice), concurrency (`SKIP LOCKED`) |
| Schema change | Migration up, down, up; constraint test for any new CHECK or unique rule |
| UI change | Component test for logic. Playwright update if a user journey changed. axe check if a page was added. |
| Bug fix | A failing regression test first, then the fix |

Rules:
- Tests use real PostgreSQL with PostGIS, never SQLite. External systems are replaced by `FakeGateway` and `MemoryStorage`.
- Deterministic: no `sleep`, no reliance on wall-clock time or test order. Seed randomness.
- Arrange, Act, Assert. One behaviour per test. Names describe behaviour: `test_second_accept_on_same_order_returns_conflict`.
- A flaky test is a bug. Fix or quarantine with an issue link and a deadline. Never retry-until-green.
- Coverage floor: 90% on `domain` and `services`, 80% overall. Coverage is a floor, not proof.
- When a change touches an invariant in `DATA_MODEL.md`, update the invariant and its tests together.

## 9. Security checklist (apply to every change)

- [ ] Input validated at the boundary, with limits (size, length, range).
- [ ] Authentication required unless explicitly public. Object-level authorization in the service.
- [ ] No secrets, tokens, PDF content or personal data in logs or error messages.
- [ ] No raw SQL string building. Use bound parameters.
- [ ] File paths and storage keys never derived from user input.
- [ ] Rate limits on any endpoint that can be brute forced or is expensive.
- [ ] Webhooks verified on raw bytes with constant-time comparison.
- [ ] New dependency checked, pinned, and covered by the audit tools.

## 10. How to work (agent workflow)

1. **Restate the task** in one or two sentences with the requirement ID and sprint. Confirm it is in scope.
2. **Plan before coding** when the change touches more than three files, or any schema, money, authentication, authorization, payment, or privacy logic. Write the plan: files, approach, tests, risks. If an ambiguity affects those areas, ask before building.
3. **Build the thinnest vertical slice** that proves the behaviour. For domain logic, write tests first.
4. **Keep diffs small and focused.** No drive-by refactors, formatting churn, or unrelated fixes. Note them as follow-ups instead.
5. **Verify.** Run `make check`, plus the relevant narrower tests. Run the app and exercise UI changes in a browser at phone and desktop width when you can.
6. **Update docs and ADRs** when behaviour, API, schema, or a decision changed.
7. **Report back** using the format in section 11.

### When to stop and ask

Stop and ask rather than guess when:
- The request touches money, authorization, privacy, or migrations in a way the docs do not cover.
- The docs conflict with each other or with the code.
- The task needs out-of-scope work, a new dependency, new infrastructure, or a new external service.
- A test fails and the right fix is unclear, or the test itself looks wrong.
- You would need to delete or rewrite significant existing code.

### Honesty rules

- Never claim tests pass, a command succeeded, or a feature works unless you ran it and saw the result. If you could not run something, say exactly what you did not verify.
- Never present simulated or seeded data as real. Label it.
- If you are not sure about a library behaviour, check the documentation or write a small experiment. Do not rely on memory for exact APIs.
- Report unfavourable findings plainly: a flaw in the design, a requirement that is overbuilt, a metric that missed its target.

### Teaching mode

The owner is a student using this project to learn and to explain it in interviews. When you make a non-obvious choice, explain the reasoning briefly in the PR description or an ADR, and mention one alternative you rejected. Prefer code the owner can read and defend over code that is merely short.

## 11. Report-back format

End every task with:

```
Summary: one or two sentences.
Requirement: FR-x (sprint N)
Changed: key files and what changed in each
Verification: exact commands run and results (pass counts, coverage if relevant)
Not verified: anything you could not run or check
Risks and follow-ups: edge cases, debt, parking-lot items spotted
Docs and ADRs: updated or created
```

## 12. Definition of done

- [ ] Requirement ID identified and acceptance criteria met
- [ ] Tests at the right level, including failure and authorization cases, passing in CI
- [ ] `make check` passes locally with no new warnings
- [ ] Migrations reversible and backward compatible, constraints tested
- [ ] No secrets, no stray debug code, no unrelated changes
- [ ] Docs, invariants and ADRs updated where behaviour or decisions changed
- [ ] UI: loading, empty and error states, keyboard use, phone and desktop width checked
- [ ] Report-back written honestly

## 13. Phase gates

Do not start the next phase until the current gate in `IMPLEMENTATION_PLAN.md` is fully checked. If a gate item cannot be met, record why and get an explicit decision to proceed. Do not quietly skip it.

## 14. Known pitfalls in this codebase

- Float or decimal money creeping in through JSON, JavaScript numbers, or Python `/` division. Use integers and `//` or explicit rounding at the edges only.
- Trusting the price, status, or user id sent by the client.
- Verifying the webhook signature on parsed JSON instead of the raw body.
- Forgetting `uploads.delete_after` handling on a new terminal path, leaving files stored forever.
- Assigning `order.status` directly in a new code path, bypassing events and refund logic.
- Swapping latitude and longitude. PostGIS `ST_MakePoint` takes longitude first.
- UTC versus IST confusion. Store UTC, format in `Asia/Kolkata` in the UI only.
- Running PyMuPDF or OpenCV inside an async or request path. Use the worker.
- Stale TanStack Query caches after mutations. Invalidate the keys.
- Polling continuing for terminal orders or hidden tabs.
- Windows line endings breaking shell scripts or Docker builds. `.gitattributes` forces LF.
- Docker Compose services starting before the database is ready. Use healthchecks and `depends_on` conditions.
- In-memory rate limiting and WebSocket hubs silently breaking when a second API instance is added. This is a documented limit, not a bug to patch locally.
- Treating a green CI as proof of correctness for money and authorization code. Review those paths by reading them.

## 15. Task brief template (for the owner)

Use this shape when asking an agent for work. It produces better, safer results.

```
Task: <one sentence>
Requirement: <FR id from the PRD>, sprint <N>
Context: <anything the docs do not already say>
Constraints: <must and must not>
Acceptance: <observable behaviours or tests that must pass>
Out of scope: <what to leave alone>
```
