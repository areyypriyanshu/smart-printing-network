# ADR 004: The signed webhook, not the browser, decides that an order is paid

Date: 2026-10-19
Status: Accepted
Requirement: FR-8, FR-9, FR-13 (order and payment)

## Context

The customer pays on a Razorpay checkout page that the browser opens. When the payment finishes, Razorpay can tell two things: the browser, through a client side callback, and us, through a signed webhook.

The browser is not a trustworthy witness. It can be closed, it can be offline, it can be lying, and anyone can call our API with a made up callback. If the browser could mark an order as paid, then anyone who wanted a free printout could simply send the callback themselves. If we only trusted the webhook, then a customer whose browser closed after paying would see an order stuck in PENDING_PAYMENT until it expired, even though the money had arrived.

## Decision

Only a webhook that we have verified marks an order as paid.

- The webhook endpoint reads the **raw request body** and verifies an HMAC-SHA256 signature of those exact bytes with `hmac.compare_digest`. The body is never parsed before it is verified, so a body that is valid JSON but different from the body that was signed cannot pass.
- The event id in the `X-Razorpay-Event-Id` header is the primary key of the `webhook_events` table. A duplicate delivery finds the row and does nothing.
- The amount and the currency in the event must match the order. A mismatch is logged and the order stays pending, so it expires rather than being delivered for free.
- A late payment, one that arrives after the order expired or was cancelled, is captured and immediately queued for a refund. The customer is never charged for an order that will not be printed.
- The browser callback does nothing but start polling. The frontend never decides that an order is paid.

## Alternatives considered

1. **Trust the browser callback.** Rejected: it is trivially forgeable. Anyone who reads the frontend bundle could mark any order as paid.
2. **Poll the gateway for the payment status instead of taking a webhook.** Rejected: it puts the gateway on the critical path of every order, it burns gateway rate limit, and it is slower. A webhook is the provider telling us the moment something happened.
3. **Trust the webhook without checking the amount.** Rejected: the amount check is what stops a payment of one rupee from delivering a hundred rupee printout. It is one comparison, and it is the difference between a marketplace and a charity.

## Consequences

- The order exists before the payment starts, so a late or a duplicated webhook always finds a row to reconcile against.
- The pickup code is generated only when the payment is confirmed, so an unpaid order never carries a usable code.
- If our webhook endpoint is down, no order is marked paid. The provider retries, and the endpoint returns 5xx on an internal failure so that it does.
- The customer may see a short wait after paying while the webhook lands. The UI says "confirming your payment" rather than pretending the payment is done.
- The webhook path is the part of the system that has to be right. It has the most adversarial tests: forged signature, duplicate delivery, parallel duplicate delivery, wrong amount, wrong currency, late payment on an expired order, and a body that is valid JSON but not the body that was signed.

## Revisit trigger

If a payment provider offered a signed server to server call that could be verified synchronously during the checkout request, the webhook would become a confirmation rather than the source of truth, and the "confirming your payment" wait could go away.
