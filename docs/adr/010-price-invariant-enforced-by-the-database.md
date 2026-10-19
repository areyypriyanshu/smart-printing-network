# ADR 010: The price rule is enforced by a database constraint

Date: 2026-10-19
Status: Accepted
Requirement: FR-6, FR-8 (price and order), invariant I1 in DATA_MODEL

## Context

The price of an order is `max(page_count x copies x rate_paise, min_order_paise)`. The rate comes from the shop, the page count from the file the customer uploaded, and the minimum from the shop settings.

This is the one number in the system that money depends on. If it is ever wrong, a customer is charged the wrong amount, or a shop prints for free, or a refund is the wrong size.

The application computes the price in one place, `domain/pricing.py`, and calls it from both the quote path and the order path. That is good, and it is not enough. An application bug, a migration, a script run by hand, or a future code path that builds an order by hand can all write a price that no formula would produce.

## Decision

The rule is also a constraint in the database:

```sql
CHECK (price_paise = GREATEST(page_count * copies * rate_paise, min_order_paise))
```

The order stores the inputs as well as the result: `page_count`, `copies`, `rate_paise` and `min_order_paise` are copied onto the order when it is created and are never changed afterwards. The constraint is therefore checkable at any time, not only at the moment the order is written.

A second constraint keeps the paid side honest: an order that is `PAID` or later must have both a `paid_at` and a six digit `pickup_code`, so an order can never be paid without a code that the customer can show.

The application still computes the price. The constraint is the backstop, not the calculation.

## Alternatives considered

1. **Trust the application.** Rejected: a constraint that only exists in code is only as strong as every code path that writes the row, now and in the future. There are several ways to write an order: the API, the CLI, a job, a script, a data fix.
2. **Recompute the price in a trigger.** Rejected: a trigger hides the calculation from the application and from anyone reading the code, and it makes the "one source of truth" claim false. The constraint does not calculate anything, it only refuses a value that does not fit.
3. **Check the price in the service only.** Rejected: that is the same as trusting the application, with a test instead of a constraint.
4. **Do not store the inputs, only the result.** Rejected: then the constraint has nothing to check, and the audit trail of "what was this order worth and why" is lost.

## Consequences

- A wrong price cannot be stored. The insert fails and the transaction rolls back.
- The test suite has a case that tries to store a wrong price and expects the database to refuse it. That test would fail the moment the constraint was dropped.
- The database has to be migrated before the code that relies on the new column exists, which is the expand and contract order the migration policy already requires.
- The constraint cannot express every rule. It can check that the price fits the formula, but it cannot check that the rate came from the shop that the order is for, because a check constraint cannot see another table. That check stays in the service, where the transaction can do it.
- The order keeps a copy of the rate, so changing the shop's rate later never changes an order that already exists. The test for that is `test_rate_change_after_creation_does_not_change_the_order`.

## Revisit trigger

If the price ever stops being a pure function of the order's own columns, for example if it depends on a discount table, move that part of the rule into the service and keep the constraint only for the part that is still local to the row.
