# ADR 014: A narrow admin panel, not a general one

Date: 2026-10-24
Status: Accepted
Requirement: FR-2 (Sprint 5.6)

## Context

A shop that registers itself starts unverified, and an unverified shop
cannot take orders. Somebody has to decide when a shop becomes verified.
Until now that somebody has been the operator, running a command on the
server:

```
docker compose run --rm api python -m app.cli verify-shop owner@example.com
```

That works, and it is the right amount of tooling for the first ten
shops. It stops being the right amount of tooling at about the eleventh,
for three reasons.

The command needs an email address, and there is no way to find out
which shops are waiting. The operator has to run a SQL query by hand
first, which means a command that only the person who wrote the SQL can
use.

The command can only approve. There is no way to take a shop off the
market, and no way to force a shop to stop accepting orders, because
`accepting_orders` is a field the shop controls. A shop that stops
answering its customers, or that is caught doing something dishonest,
stays on the platform until the operator edits the database.

And the decisions leave no record. A verification is a decision about
somebody else's business, made by a person, and nothing says who made it
or when.

The schema already had the answer in it. `ck_users_role` has always
allowed `admin`, and `schemas/auth.py` has always typed the role as
`Literal["customer", "vendor", "admin"]`. The role existed and nothing
used it.

## Decision

One admin role, one screen, two buttons, and a log.

### What the admin can do

Exactly two things: approve a shop, and suspend a shop. Nothing else.
There is no admin endpoint that can read a customer's orders, see a
customer's uploads, move money, or issue a refund. There is no admin view
of the platform's revenue.

The reasoning is that the admin's job is narrow. The admin decides which
shops are allowed to take orders. Every endpoint that is not about that
is scope that nobody has asked for, and scope that nobody has asked for
is where the security holes are. The strongest version of this decision
is the version where the admin cannot do much, because a role that can do
little has little to attack.

### How an admin account comes to exist

Only from the command line:

```
python -m app.cli create-admin owner@example.com <password>
```

There is deliberately no endpoint that creates an admin. An admin is the
person who decides which shops are allowed to take orders, so an open
signup for one would hand that decision to whoever found the form
first. The operator who can run `docker compose exec` already holds the
server; the account is a convenience for them, not a security boundary
in its own right. The real boundary is the database and the server
access, and that is where it already was.

### Every decision is recorded

`admin_actions` holds one row per decision: which admin, which shop,
what was decided, when, and for a suspension, why. The row is written in
the same transaction as the change to the shop, so the log cannot
disagree with the state.

The table has a sequence primary key rather than a UUID, for the same
reason `order_events` uses one. `now()` is the time the transaction
started, so two decisions taken in the same transaction carry the same
timestamp, and a UUID tiebreaker would order them at random. A sequence
gives the tie a deterministic answer, so the newest decision really is
the newest one.

`admin_id` is nullable, and the null means the decision was taken from
the command line by the operator, who is not an admin account. The
command line is a real actor, and the log should say so rather than
pretend a person did it.

### A suspension does not touch orders

This is the decision in this ADR that matters most, and it is the one
that is easiest to get wrong.

Suspending a shop sets `is_verified` to false and `accepting_orders` to
false, and changes nothing else. The shop stops getting new orders. Its
existing orders stay exactly where they are.

The temptation is to also reject the shop's unaccepted paid orders, so
that customers of a suspended shop are refunded promptly. That is wrong.
A customer who has already paid for a printout is owed that printout, and
the shop that is printing it still has to be able to finish it. Rejecting
those orders on a moderation decision about the shop would punish the
customer for something they did not do, and it would move money back to
customers whose printers are already running. The shop's orders are
therefore left alone, and the shop simply stops receiving new ones. The
auto-reject job already handles a shop that stops paying attention, with
a refund, on its own schedule.

### The panel is one route

`/admin/shops`. A list of shops with a filter, an Approve button, a
Suspend button that asks for a reason, and the moderation log underneath.

There is no admin layout, no admin navigation tree, and no generic
resource browser. The role is `admin`, the route is one page, and the
page has one job. The existing `RequireRole` guard does the
authorisation on the client, and the server does the real authorisation
with `require_role("admin")` on every endpoint.

## Alternatives considered

1. **Keep the command line only, and make it good.** Rejected as the
   whole answer, but kept as part of it. The command line stays, and
   gains `list-shops`, `suspend-shop` and `create-admin`, because a
   server with no admin account set up yet still has to be operable. It
   is the fallback, not the product.
2. **A general admin panel, with a resource browser for every table.**
   Rejected: this is where admin panels grow. Every table that becomes
   browsable is a table whose data leaks, and the reasoning for each one
   has to be made again. The verification queue is the job.
3. **A separate admin database, or a separate admin authentication
   system.** Rejected: the `admin` role already exists in the schema
   and works with the login, the token, the refresh rotation and the
   guard. A second authentication system would be more code and more
   ways to be wrong, for a role that has one page.
4. **Let shops self-verify, and let the platform spot problems later.**
   Rejected: the whole point of the panel is the decision. A platform
   where any shop can list itself is a directory, not a marketplace, and
   a student who is scammed by one shop is a student who does not come
   back.
5. **Let the admin edit a shop's rates or details, not just verify it.**
   Rejected for now. It is a natural next step, and it is also a much
   bigger surface, because the admin would be editing another tenant's
   commercial data. The same authorisation rules would apply, and the
   temptation to make the admin a superuser would grow. Revisit when
   there is a real need.

## Consequences

- A new admin can be created in one command, and a shop can be approved
  from a browser.
- The verification queue is ordered oldest first, so the shop that has
  been waiting longest is at the top. The customer facing shop list is
  ordered by price, and the two are deliberately different.
- Every decision is in `admin_actions`, and the log is readable from the
  panel or from the database.
- Suspending a shop is safe for the customers who already paid.
- Two new error codes, `SHOP_ALREADY_VERIFIED` and `SHOP_NOT_VERIFIED`,
  because the generic `CONFLICT` message ("this was just updated
  elsewhere") tells an admin nothing about why their click did nothing.
- The admin role can see shop contact details. That is the only personal
  data the admin role can reach, and it is the data needed to check that
  a real person is behind a business.
- The `admin_actions` table is append only. There is no endpoint that
  edits or deletes a row, and none should be added.

## Revisit trigger

Revisit when the owner needs to do something the panel cannot do, and
that something is about shops rather than about orders or money.

The trigger is a specific request: an admin needs to correct a shop's
address, a shop needs its rates corrected, or the verification queue has
so many shops that a single list stops being workable. At that point the
decision is about how much admin power to build, and it belongs in its
own ADR. If the request is ever about orders, money or customers, that
is a different feature and a much larger decision, and this ADR's
principle, that the admin role stays narrow, is the thing to argue
against.
