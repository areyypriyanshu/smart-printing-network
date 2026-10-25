# ADR 022: The webhook event and the payment it causes are one transaction

Date: 2026-10-19
Status: Superseded by ADR 035 (cash only)
Requirement: FR-8, FR-9, FR-13 (order and payment)

## Context

A payment provider delivers a webhook. We have to do three things with it: remember that it arrived, so the same delivery is not applied twice; apply the effect, which is usually moving an order to PAID; and mark the event as applied.

The order of those three, and the transaction boundaries around them, decide what happens when something goes wrong in the middle.

The version this replaces did them in three transactions. The inbox row was committed on its own, the payment was marked CAPTURED and committed on its own, and the order was moved to PAID afterwards. That looks tidy, and it is exactly the wrong shape:

- A delivery that failed after the inbox row was written was spent. The provider retried, the retry found the event id, and the retry was told the event had already been applied. The order was never paid and the customer had paid.
- A payment that was marked CAPTURED and committed, whose order transition then failed, left a captured payment with no order behind it and no refund scheduled. The money was taken at the provider and stayed with the platform.

Both are the same mistake seen from two sides: a step whose result was written down separately from the step it was part of.

## Decision

The event and its effect are one transaction, and one transaction decides the outcome.

- The inbox row is written and flushed, not committed. The event id is not spent until the effect has been applied.
- The payment's capture and the order's transition are one operation. The transition's own commit writes the capture, the new status and the `order_events` row together.
- When the transition cannot be applied, the transaction is rolled back, the order is re-read, and the real state decides the answer:
  - the order is EXPIRED or CANCELLED: the payment is recorded as REFUND_PENDING **with** a next-attempt time, so the refund job picks it up;
  - the order is PAID: the delivery is answered as already applied, which is what two events for one payment mean together;
  - the order is anything else, including still PENDING_PAYMENT: the delivery is answered 503 PAYMENT_NOT_APPLIED. The provider retries, and the retry can still apply it, because nothing was recorded as applied.
- A duplicate is decided by `processed_at`, not by the existence of the row. An event that was recorded but not applied is not a duplicate.

The refund job also picks up a payment that is REFUND_PENDING with no next-attempt time. The next-attempt time is the schedule, not the permission: a writer that forgot to set it must not leave the money in the platform's pocket for ever.

## Alternatives considered

1. **Keep the inbox row committed first, and treat the existence of the row as "already handled".** Rejected: a failed delivery is then spent, and the provider's retry is silently ignored. The customer has paid and the order is not paid.
2. **Keep the capture in its own transaction, and reconcile later.** Rejected: it needs a reconciliation job for a case that a single transaction makes impossible, and the window where the money is captured with no order behind it is exactly where a bug becomes a lost customer.
3. **Answer every failed transition with "already paid".** Rejected: it is a lie when the order is still waiting for its payment, and it hides the case that needs a retry. The answer has to follow the order's real state.
4. **Schedule the refund only through the order's cancel or expire path, and not in the webhook.** Rejected: the webhook is the only place that knows the money arrived after the order went away.

## Consequences

- The webhook endpoint answers 5xx when the payment could not be applied, and the provider retries. The customer sees a short wait rather than a lost payment.
- A duplicate delivery of an event that was applied is answered as a duplicate and does nothing, which is the rule the webhook contract asks for.
- The webhook path has more tests: a delivery that failed and was retried, a payment that lands on an expired order, a payment that lands on a cancelled order, a transition that is refused, and two deliveries at the same moment for one payment.
- The rule that only `OrderService.transition()` writes `orders.status` is what makes this work: the payment service cannot move an order by assigning to it, so the capture and the status change are forced to travel together.
- The answer to a failed transition depends on reading the order again, so the transition has to fail for a reason the payment service can classify. Anything it cannot classify is answered 503, which is the safe answer: the provider retries and nothing is lost.

## Revisit trigger

If the provider offered an idempotent "capture and confirm" call the platform could make itself, the capture and the webhook would not have to be reconciled against each other at all, and this transaction would disappear.
