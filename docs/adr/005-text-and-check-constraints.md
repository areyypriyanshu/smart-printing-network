# ADR 005: Text columns with CHECK constraints instead of Postgres enums

Date: 2026-10-19
Status: Accepted
Requirement: all Phase 1 tables, ADR 010 (price invariant)

## Context

Every categorical value in this system is a short string with a known set of values: an order status, a paper size, a payment status, a user role, an actor type. PostgreSQL can express that in two ways: a native `ENUM` type, or a `text` column with a `CHECK` constraint.

The values are not fixed for ever. An order will probably gain a status, a payment may gain one, and a role may gain one. Every change has to be a migration, and a migration has to work on a database that already holds rows.

## Decision

Use `text` with a named `CHECK` constraint, for example:

```sql
status text NOT NULL CHECK (status IN (
  'PENDING_PAYMENT','PAID','ACCEPTED','PRINTING','READY',
  'COLLECTED','REJECTED','CANCELLED','EXPIRED'))
```

The constraint is named (`ck_orders_status`) so a failure says which rule was broken and not just which table.

The same rule is written down once in the domain layer (`app/domain/order_state.py`) and once in the model (`app/models/order.py`), and the test suite checks that the two agree. The domain copy decides what the application may do; the database copy makes it impossible to store something the application would never do.

## Alternatives considered

1. **Postgres `ENUM` types.** Rejected: adding a value to an enum inside a transaction is not allowed in the version this project would run on, so a new status means a lock, a manual `ALTER TYPE` outside the migration, and a careful deployment order. A `CHECK` constraint is a normal migration that can validate existing rows and be rolled back.
2. **A lookup table with a foreign key.** Rejected for now: it adds a join to every read and a second place to keep in step, and buys nothing while the values are a closed set written by this project alone. A lookup table becomes the right answer when the values are data rather than code, for example a table of paper sizes that a shop owner can add to.
3. **No constraint at all.** Rejected: a typo in a status string would then be storable, and the state machine would meet it at runtime.

## Consequences

- Adding a status is an ordinary migration: a new `CHECK`, a new domain constant and a new transition.
- The values are readable in the database without knowing the type.
- A query comparing a status is a plain text comparison, with no enum cast.
- The check constraint and the domain rule are two copies of the same fact, so they can drift. The test that compares them is what keeps them honest, and it is the reason that test exists.

## Revisit trigger

If the set of values ever becomes data that a user can change, for example paper sizes an operator adds, move to a lookup table with a foreign key and keep the constraint only for the values that stay closed.
