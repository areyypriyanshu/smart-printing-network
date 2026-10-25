# ADR 035: Cash at the counter, and no online payment path

Date: 2026-10-25
Status: Accepted
Requirement: FR-8, FR-11, FR-13, Sprint 11.9

## Context

The first version of this project took money online through Razorpay in
test mode. Because no real money ever moved, most of what that path added
was cost rather than value: a gateway adapter, a signed webhook with its
own inbox, amount and currency checks, refunds and their retry schedule,
a "simulate payment" endpoint for local demos, provider credentials in
every environment, a payment script in the page and a corresponding hole
in the content security policy.

All of that existed to make a test-mode payment look real. It also made
the product harder to explain: the interesting decisions were buried
under a payment integration that could not be used for real, while the
handover — the pickup code and the cash at the counter — was already
built and is the part a shop actually performs.

The owner decided to remove online payments entirely rather than disable
them. This ADR records that decision and what was kept.

## Decision

An order is a cash reservation from the moment it is placed. There is no
online payment step.

- `POST /orders` creates the order as `RESERVED`, issues the pickup code
  immediately, and writes one `payments` row with provider `cash`,
  status `CREATED` and the server-computed amount. The idempotency key
  and the price rules are unchanged.
- The vendor accepts, prints and marks the order ready as before.
- Collection is the settlement. The vendor verifies the pickup code in
  constant time, and the transition to `COLLECTED` sets `paid_at` and
  moves the payment row to `CAPTURED`. The status change, the
  `order_events` row and the capture commit in one transaction, so a
  collected order cannot exist without a recorded payment.
- A second collect attempt finds the order already `COLLECTED` and is
  refused by the state machine; a concurrent race is decided by the same
  compare-and-swap that guards every transition.
- There is no refund path. `expire_no_shows` only expires ready orders
  whose `payment_method` is `at_store`, because a historical online order
  has no automatic way to return money.

### What was deleted

The payment gateway interface and both implementations, the payment and
refund services, the Razorpay webhook route, the testing route that
simulated a payment, the refund retry job, the provider settings, the
frontend checkout script, and the Razorpay allowance in the content
security policy. Tests that existed only for those paths were removed
with them.

### What was kept, and why

The `payments` and `webhook_events` tables, the `PENDING_PAYMENT` and
`PAID` statuses, the refund columns and every merged migration stay as
they are. Historical orders must remain readable, and the identity
provider's webhook still uses `webhook_events` for delivery
deduplication. No new migration was needed, and no merged migration was
edited. ADR 004, ADR 009 and ADR 022 are marked superseded; ADR 013
(cash on collection) becomes the only payment path instead of the second
one.

The `Payment` model stays as a ledger row. It is what lets a collected
order show that money was recorded, and it keeps historical rows
queryable without a second table for old data.

## Alternatives considered

1. **Disable online payment with a feature flag and keep the code.**
   Rejected: a payment module that can still charge is a liability even
   when the configuration says not to call it, and code that no test
   exercises rots. Deleting it also removes its configuration, its CSP
   allowance and its documentation surface.
2. **Keep the fake gateway so demos can still show a checkout.**
   Rejected: the fake checkout asks a customer to "pay" in a simulation,
   which is less honest than the real flow the shop performs. Cash at the
   counter is the product, not a stand-in for it.
3. **Migrate historical orders to the cash lifecycle.** Rejected: it
   would rewrite what happened, need a migration over merged history, and
   still not make an old online order collectable in cash. Reading the
   old states is enough.
4. **Drop the `payments` table and start over.** Rejected: it discards
   the record of historical orders and the audit trail of what was
   captured, for no gain now that the online path is gone.

## Consequences

- The project no longer claims an online payment integration. The
  README, the architecture and the test report say cash at the counter.
- The money path is shorter and testable end to end: reservation, price
  constraint, constant-time pickup code, capture at collection in one
  transaction, and a no-show expiry that cannot touch cash that was never
  taken.
- The platform cannot verify that cash changed hands. The vendor's
  Collect action is the record, and a dispute about whether notes were
  handed over is outside the system's control.
- There is no automatic refund. A historical `REFUND_PENDING` row left
  by the online version is a manual handling item, recorded as a residual
  risk in the security review.
- Reintroducing online payment is a new project, not a flag: it needs a
  gateway, a verified webhook, refunds, tests and a new ADR. ADR 004,
  ADR 009 and ADR 022 remain as the blueprint for what that has to get
  right.

## Revisit trigger

If the product needs money before the printout exists — to stop
no-shows, to serve customers who cannot come to the counter, or to pay
vendors — reintroduce one online provider behind a protocol, with a
signed webhook as the source of truth, and write a new ADR that
supersedes this one.
