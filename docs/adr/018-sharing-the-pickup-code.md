# ADR 018: Sharing the pickup code, and who that trusts

Date: 2026-10-20
Status: Accepted
Requirement: FR-17 (Sprint 6)

## Context

The pickup code is the whole handover mechanism. The shop checks six
digits against the order and hands over the printout. The code is
issued when the order is paid, never changes, and is only ever shown to
the customer who owns the order.

The code is already transferable by design. Nothing about it is bound to
the person who paid. The only thing missing is a way to hand it over
quickly.

That matters because a lot of pickups are not the person who ordered. A
roommate collects. A friend picks up for a lab partner. A student is in
a hurry and someone else is going to the shop. Today the only way to do
that is to read six digits out loud, or to type them into a message by
hand, which is exactly the kind of friction that makes people pick the
job up tomorrow instead.

The request was: `wa.me/?text=` with the code in it. No business API, no
cost, no integration.

## Decision

A "Share the code on WhatsApp" button on the order page and on the
wizard's paid and reserved screens. It opens a `wa.me` link with the
order number, the shop name and the code already written.

That is the whole implementation. There is no WhatsApp Business API, no
webhook, no message template, no conversation stored on our side. The
link is a plain web link; WhatsApp is the customer's own phone.

### The privacy part, stated plainly

The code is a bearer token. Whoever has it can collect the printout.

That is already true, and the feature makes it more obvious, so the
interface says it: *"Somebody else can collect it for you. Anyone with
this code can, so send it only to the person you trust."* The sentence
is next to the button, not in a policy page.

The platform does not weaken the code to make sharing safer. It is six
digits, it is rate limited to five wrong attempts per order per ten
minutes, and the shop still has to find the order. Sharing the code
does not let anyone see the file, read the order history or find the
customer's details: the code opens one order at one shop.

## Alternatives considered

1. **WhatsApp Business API with a template message.** Rejected: it
   costs money, it needs a business account and a verified sender, and
   it puts a message queue and a delivery-status table in the path of
   the simplest possible action. The `wa.me` link does the same job for
   the customer at no cost and with no state on our side.
2. **Email or SMS notifications.** Rejected, and already out of scope in
   the PRD. They need a provider, they cost money per message, and they
   put the customer's phone number in a third party's hands.
3. **A one time pickup link instead of a code.** Rejected: it is a
   bigger change to the handover mechanism and the vendor board, and it
   would need its own revocation story. The six digit code is the
   established mechanism, and the rate limit on wrong attempts is
   already proven.
4. **Do not build it, and let people read the code out.** Rejected: the
   friction is small but real, and it costs one anchor element to
   remove.

## Consequences

- The share button is an ordinary link. It is not a button that calls
  an API, so there is nothing to fail, nothing to rate limit and
  nothing to test beyond the link it builds.
- The order page now fetches the shop it is about, to put the shop's
  name in the message. That is one extra request on a page that already
  shows the order.
- The customer who shares the code shares it over WhatsApp, on their own
  phone. The platform does not learn that it happened, and does not
  need to.
