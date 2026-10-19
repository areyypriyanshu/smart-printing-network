# ADR 013: Cash on collection, as a second payment method

Date: 2026-10-20
Status: Accepted
Requirement: FR-8, FR-9, FR-10, FR-11, FR-13 (Sprint 5.5)

## Context

An order is paid online today. The customer pays by card or UPI through
Razorpay, the provider sends a signed webhook, and the webhook is the
only thing that marks the order paid.

That flow loses a lot of orders, and it loses them for a reason that has
nothing to do with money: the customer has no card, or no UPI balance, or
is on a connection that cannot reach a payment gateway.

The customer this hurts is a student uploading a project at 2am. The
order is 60 to 240 rupees. For that size, the online flow's friction is
proportionally enormous: a redirect, a UPI PIN, and then a wait for a
webhook that the customer has to be told not to interrupt. A gateway fee
of about 2% of a 120 rupee order is about 2.40 rupees, which sounds like
the reason to do this.

It is not the reason. 2.40 rupees on a 120 rupee order is real money to
the platform, but it is roughly 20% of a 10% commission on that order,
and the customer who cannot pay online is not going to pay 2.40 rupees
more to avoid a redirect. The reason is conversion. The customer who
cannot use the online flow does not place the order at all, and the shop
never sees the work.

### The trap

If the customer pays cash and the platform takes nothing, the platform is
a free directory. The shop receives exactly the same cash it would have
received from a customer who came directly, but it now has to run our
queue board, work our order lifecycle, and answer to our software. Every
rational shop owner tells the next customer to skip us.

So this change has to record everything a later take would need, even
though it does not take one now. The data is recorded. The settlement is
not built. That boundary is deliberate and it is the reason the ADR
exists.

### The pickup code is the evidence

For an online order the six digit code proves identity at the counter:
this is the person who paid. For a cash order it proves two things at
once. It proves identity, and it proves that money changed hands,
because the shop's collect action is the only record of the transaction
that happened. That record is the `order_events` row written by the
transition to `COLLECTED`, with `actor_type` of `vendor` and the shop's
user id.

The audit trail is therefore not decoration. It is the table a settlement
process would be built on. It has to be as strong for a cash order as
it is for an online one, and it must not be weakened to make the cash
path simpler.

## Decision

One order lifecycle, two payment methods.

- `payment_method` on the order is `online` or `at_store`.
- An online order is created `PENDING_PAYMENT` and becomes `PAID` when
  the signed webhook arrives. Unchanged.
- A cash order is created `RESERVED` and never passes through
  `PENDING_PAYMENT` or `PAID`. The money changes hands at the counter,
  and the order becomes `PAID` at the moment of collection, which is
  when `paid_at` is set.
- Everything after that is the same. Same pickup code, same vendor
  queue, same accept, start, ready and collect endpoints, same rate
  limiting on the code, same `order_events` trail.

The gateway becomes a router. `PaymentGateway.create_order` takes a
`method` argument. The router dispatches `at_store` to a `CashGateway`
and everything else to the online provider. The cash gateway never
verifies a webhook, because a signature check that could pass would be a
hole in the payment path, and it never refunds, because cash cannot be
refunded through an interface. The router sends both of those to the
online provider, so a cash payment can never reach the online refund
path even by accident.

The cash capture happens inside `order_service.transition()`, not in the
vendor service that asks for the collection. The status change, the
event row and the payment capture commit in one transaction. A collected
order with no recorded payment would be a sale that nobody recorded,
and the whole settlement case rests on that record existing.

### What is recorded, and what is not

Recorded, and nothing more:

| What | Where |
|---|---|
| The amount to collect | `orders.price_paise` |
| The method | `orders.payment_method` |
| The provider actually used | `payments.provider` |
| When the money changed hands | `orders.paid_at` |
| Which shop | `orders.shop_id` |
| Who took the money | `order_events.actor_type = 'vendor'` |

Not built: settlement, commission, payouts, invoices, GST, subscriptions.
No commission column, no payout table, no invoice. Those are a later
decision, and the data above is what it will need.

### The feature flag

`CASH_AT_STORE_ENABLED` is off by default in the code. A deployment
that has never heard of this feature cannot create a cash order by
accident, and the local `.env` turns it on for development.

The flag also protects the deploy. The migration is expand only, so the
old application version works against the new schema. But the old state
machine has no `RESERVED`, so an order in that state cannot be moved by
the old code. Rolling back to the old image while cash orders exist
leaves those orders stuck. With the flag off, no cash order can exist,
so the rollback is safe. Turning the flag on is a decision that the
owner makes deliberately, with the hazard in view.

## Alternatives considered

1. **Drop online payment entirely.** Rejected: it would remove the
   payment provider's webhook as the source of truth, which is the
   strongest single guarantee in the money path, and it would make
   every order wait for a human at a counter. Online payment is the
   default for a reason.
2. **A subscription model: pay monthly, print all year.** Rejected: it
   inverts the relationship. A student uploading one project at 2am
   does not want a subscription, and a shop that has to check whether a
   customer is current cannot hand the printout over. It also needs a
   much larger change to the order model, and it puts the conversion
   problem back in front of the customer.
3. **A separate basket or payment group model, where cash orders live
   in their own tables.** Rejected: it would mean two queues, two
   lifecycles, two pickup code paths and two audit trails for the same
   physical work at the same counter. The shop would have to decide which
   board to look at, and the customer's order would exist in two
   shapes. The whole value of this change is that it is *one* order
   with two ways to pay for it.
4. **Keep one order per document, but let the customer pay part online
   and part in cash.** Rejected: partial payments need a new money
   model, a new status for "part paid", and a way to refund a part.
   That is a much larger change than the one this problem needs.
5. **Collect cash, but have the platform take the money at the counter
   as well.** Rejected: it needs a card machine at every shop, a
   settlement relationship with the shop, and the same payout machinery
   this change is explicitly deferring.

## Consequences

- The order lifecycle is one thing. The vendor board does not know or
  care which method an order uses, except that a cash order says so and
  the shop knows to expect money at the counter.
- A cash order never enters `PAID` until it is collected, so a shop
  that ignores it is auto-rejected after the accept window with no
  refund, because no money was taken. A cash order that is ready and
  never collected is expired after the no-show window, which releases
  the file.
- The refund path is untouched. `RESERVED` is not a refundable state,
  so rejecting or cancelling a cash order queues no refund, and the
  existing `queues_refund` rule decides that rather than a special
  case in the code.
- The webhook is untouched. It still marks only online orders paid, and
  a webhook that names a cash order does nothing.
- Two constraints in the database became conditional on the payment
  method instead of being removed. An online order in `PAID` still has
  to have a `paid_at` and a pickup code. A cash order in `ACCEPTED`
  legitimately has no `paid_at`, because the money has not changed
  hands yet.
- The `pickup_code` column now means two slightly different things:
  "issued when the order was paid" for an online order and "issued when
  the order was reserved" for a cash one. It is still six digits, still
  from a cryptographic source, still constant-time compared and never
  changes once issued.
- The queue is ordered by `reserved_at` rather than `paid_at`, because
  a cash order has no `paid_at` until it is collected and would
  otherwise sort last in the shop's queue forever.
- **The rollback hazard.** With the flag on, a rollback to the previous
  image leaves `RESERVED` orders unmovable, because the old state
  machine has no such state. The mitigation is the flag: it is off by
  default, and turning it on means accepting that hazard, or draining
  the cash orders first.

## Revisit trigger

This ADR is about recording, not about taking money. It should be
revisited when the order volume makes a real settlement worth building.

The trigger is a number, not a feeling: when a shop collects enough
cash orders in a month that the platform's cut would pay for the
payout machinery, and the shops are asking to be paid on a schedule
rather than in cash at the counter. At that point the decision to build
a payouts flow belongs in its own ADR, with the commission model, the
payout schedule, the tax treatment and the reconciliation against
`order_events` worked out properly.

The number to watch is the monthly cash order volume per shop. While
that volume is low, the platform is running its board for free, and the
fix for that is a commercial conversation, not a technical one.
