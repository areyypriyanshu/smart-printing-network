# ADR 034: Live updates over an authorized WebSocket, with polling as the fallback

Date: 2026-10-25
Status: Accepted
Requirement: FR-32, Sprint 10

## Context

ADR 007 put polling in Phases 1 and 2 and named the trigger for a WebSocket:
the live queue and the wait estimates arriving in Phase 3. Both are here now.
A shop watching the board waits up to five seconds to see a new paid order, and
a customer watching an order page waits up to five seconds to see it move to
printing or ready. The estimate work added a second reason to refresh, because
an accepted order changes what a new arrival would wait.

Polling is not wrong, but it is now the binding limit on how immediate the
product feels, and it is the traffic the API pays for while nothing changes.

## Decision

Push order status changes over an authorized WebSocket, and keep polling as the
fallback that a disconnected, blocked or hidden client always falls back to.

### Two endpoints

- `/ws/vendor` subscribes a shop's board to `vendor:{shop_id}`.
- `/ws/orders/{order_id}` subscribes a customer to `order:{order_id}`.

The channel identity is derived on the server from the authenticated account and
is never taken from the caller: a vendor's channel comes from the shop whose
`owner_id` is that user, and a customer's from an order whose `customer_id` is
that user. Another shop's or another customer's identifier is refused with the
same 404 the HTTP API gives, so a socket cannot be used to probe for one.

### Authentication

A browser cannot set an `Authorization` header on a WebSocket handshake, and the
token is not put in the URL either, because a URL is logged. The socket accepts
the `spn.v1` subprotocol and then reads exactly one
`{"type":"authenticate","token":...}` frame before subscribing. The frame is
bounded (16 KiB) and the token with it (8192 characters). The socket is
re-authorized every 30 seconds, so an account that is deactivated loses its
stream within half a minute rather than at token expiry.

The origin is checked against the configured allow-list on the same rule the
HTTP API uses, and the handshake is rate limited per client address.

### Publishing only what committed

The publish is bridged from PostgreSQL `LISTEN/NOTIFY` on the
`spn_order_transition` channel. `pg_notify` runs in the same transaction as the
`order_events` row, inside a savepoint, so it is delivered only if that
transaction commits; a rollback publishes nothing. The API listens on a
dedicated autocommit connection and fans the notification out in-process to the
sockets that asked for the channel.

Notifications are hints, not a log. A client that missed one, because it was
disconnected, because the listener restarted, or because its queue overflowed,
must re-read. The server sends `resync` when the listener recovers, and the
client invalidates its queries on every message. The payload carries no
customer or file data, and no sequential database id.

### Bounded, and honest when unavailable

Each connection has a bounded queue, and there are per-address and total
connection limits, so a slow or vanished reader cannot grow memory. When the
listener is down the hub closes every socket rather than pretend to be live,
which sends every client back to polling.

### The client

`useLiveChannel` opens one socket per page, resets its backoff only when the
server confirms the subscription, closes the socket when the tab is hidden,
reconnects with capped exponential backoff, drops a socket that has gone silent
past 45 seconds, and reports its state so the page polls exactly when it is not
live.

## Alternatives considered

1. **Server-sent events.** Rejected in ADR 007 for the same reasons, and still
   rejected: the client has one small frame to send (the token), and SSE cannot
   send one.
2. **The token in the query string.** Rejected: query strings are written to
   access logs, proxy logs and browser history. The first-frame handshake keeps
   the credential out of all three.
3. **Polling every second instead.** Rejected: it multiplies the request rate by
   five for every open tab and still has a one-second floor, where a push has
   none. It also does not show the wait estimate change with work the client
   cannot see.
4. **An external broker (Redis pub/sub).** Rejected: ADR 008 runs one API
   instance and the project deliberately has no Redis. `LISTEN/NOTIFY` is
   already in the database and needs no new component. This is the documented
   limit that returns if the API is scaled out.
5. **Polling the database for changes.** Rejected: it is a timer pretending to
   be a push, it has the same latency floor as polling, and it adds query load
   rather than removing it.

## Consequences

- A status change is visible as soon as it commits instead of within five
  seconds. Polling stays, so a browser that cannot hold a socket, a hidden tab,
  and a listener outage all still work, more slowly.
- The API is no longer stateless: the hub and the rate limiter live in the
  process. Two API instances would split the sockets and break the fan-out.
  This is recorded in ADR 008 and in the known limitations.
- `notify_transition` is best-effort by design: a failed hint is logged and
  swallowed, and a live update is never a reason to fail an order.
- The first-frame handshake and the re-authorization timer are moving parts the
  HTTP path does not have, so the refusal paths are covered by integration tests
  and not only the happy path.

## Revisit trigger

Revisit when the API has to run more than one instance, when a second process
type has to publish, or when the notification volume makes a per-connection hub
the wrong shape. The first of those means a shared transport replaces the
in-process hub; the polling fallback already means the product degrades rather
than breaks in the meantime.
