# ADR 029: Clerk proves who someone is, this database decides what they may do

Date: 2026-10-21
Status: Accepted
Requirement: FR-1, FR-19, FR-20 (Sprint 5.9, authentication provider migration)

## Context

This project has its own authentication. Argon2id hashes, a signed
JWT access token that lives in memory for fifteen minutes, a rotating
opaque refresh token in an httpOnly cookie, a hashed refresh token in
the database grouped into families so that the reuse of an old one
revokes the whole login, and a link sent to an address to prove it
belongs to its owner. It works, it is tested, and it is about nine
hundred lines across the security module, the auth service and the
verification service and their tests.

A hand written OAuth client for signing in with Google was part of
that, and it was removed when this record was written, because Clerk's
own social connections replace it and a provider cannot be left to rot
beside the thing that replaces it. See
[ADR 027](027-sign-in-with-google-without-a-new-dependency.md).

Two things changed that make it worth asking whether to keep it.

The first is that this is a portfolio project. The owner is a final
year student who will be asked about this code in interviews, and an
interviewer who asks "how do you prevent account takeover" is answered
better by a design that a stranger can follow than by a design that
needs three files and a service account to explain. That was the
reason the authentication is hand written, and the reason recorded in
[ADR 027](027-sign-in-with-google-without-a-new-dependency.md) and in
the technology stack document: *third party auth providers hide the
thing being demonstrated*.

The second is that the hand written version has grown past the part
that is worth demonstrating. Password hashing is a solved problem
written by people who spend their lives on it. Refresh token rotation
and reuse detection is a solved problem. The part of this project
that is worth demonstrating is the other half: a customer sees only
their own orders, a vendor sees only their own shop's queue, a file is
private, and the money moves only when the state machine says so. None
of that lives in the authentication code, and all of it lives in the
services.

So the question is not "is the hand written authentication good". It
is good, and it should keep working. The question is whether the
thing being demonstrated should be password hashing, or whether it
should be the ownership rules.

Clerk is a hosted identity provider. It handles sign-up, sign-in,
passwords, email verification, sessions and social sign-in, and it
publishes a signed session token that a backend verifies. It has a
free tier, and this project is well inside it.

There is a second context, which is email. The owner works with Brevo,
a transactional email platform, and the question of who sends which
message has to be settled at the same time, because Clerk sends email
and so does the application. The current application sends exactly one
kind of message: the link that proves an email address. There is no
receipt, no notification, and no campaign, because those are out of
scope in the product requirements document.

## Decision

**Clerk proves who someone is. This database decides what they may do.**

The split is the whole decision, so it is worth being precise about
it.

Clerk owns identity. It owns the password, the verification email, the
session, the social sign-in, and the token. It is the only thing that
can answer "is this request from a person who signed in, and which
person".

This application owns everything else, and keeps all of it:

- The `users` table, the roles, and the shops.
- Every ownership check, in the services, where a missing router check
  cannot leak anything.
- The rule that a cross-tenant request is a 404 and not a 403.
- The email verification state, the account state, the order, the
  money, and the file.

### The two paths, and the one point they meet

A request arrives with `Authorization: Bearer <clerk session token>`.
The backend verifies the token's signature, issuer, origin, expiry and
subject, and then looks up the local user by the Clerk subject. The
role that decides what the request may do is read from the database
row, never from the token.

The verification is behind a small interface, so the test suite never
touches the network and the business code never knows what a Clerk
token is.

A webhook carries the other direction. Clerk tells this application
when an account is created, when an address is proved, and when an
account is banned or locked, and this application writes that onto the
local row. The webhook can only do a **closed list of things**: update
the profile fields, set the email verification flag, and set the
account inactive. It cannot write a role, cannot write the Clerk
subject, and cannot reactivate an account. A webhook that can write
whatever the payload contains is a webhook that writes a role one day.

The two paths meet at one point, and this is the part worth being
careful about: **the local row is created exactly once**. Either by
the import of an existing account, or by an explicit onboarding step
where a new person says whether they are here to print or to run a
shop, and, if the latter, gives the shop's details.

There is no third path. The request path never creates a row. That
matters because `users.email` is unique, so a request that created a
row for a subject whose address already belonged to somebody else would
be a 500, and a request that created a row by matching on the address
would be an account takeover. Neither happens, because the row is
created by a step where the person is present and the decision is
server side.

### The role model does not change

A person is a customer or a vendor, and the role is chosen once and
never changes. This is not a new rule: there is no promotion path in
the code today either, and `ck_users_role` stays a single value CHECK
constraint.

A vendor is self declared, exactly as today, because
`POST /auth/register-vendor` is anonymous and public now. The shop
starts unverified and needs an admin, which is the real gate. Only
`admin` is privileged, and it is never self declared: an admin is
granted by the operator from the command line, against a Clerk subject
the operator has verified.

### The email: Clerk proves an identity, Brevo tells a customer something

These do not overlap, and it is worth saying why.

A verification link, a magic link and a password reset link all carry
a token that only the identity provider can validate. They must come
from Clerk. Clerk cannot be pointed at a different SMTP server; the
whole point of the link is that the provider minted it.

An order receipt, a "your print is ready" notice and a campaign carry
no such token. They belong to the application, and they belong to
Brevo, which is already a decision the owner has made for their other
work.

So the rule is: **Clerk sends every message that proves an identity,
and Brevo sends every message that tells a customer something.** The
application keeps its `EmailSender` interface, which is already a
protocol with a test double, exactly like `PaymentGateway`. Brevo
plugs into it with no code at all, because Brevo speaks SMTP and the
`SMTP_*` settings already exist.

In practice this application sends no product email yet, so after the
migration the email gateway is waiting for the notification backlog
rather than doing anything. It is not deleted, because it is the seam
the backlog will need.

### The address is proved by the provider, and the application stops asking

The provider's instance asks for an address to be proved before it lets
anybody sign in, so a session that exists means the address behind it
was proved. The application used to keep its own answer to that
question, in a column, and refuse the upload while it was false, and
put a banner at the top of every page for a customer whose answer was
not yet true.

All of that is gone, and the reason is worth writing down: a copy of
an answer that another server owns can only ever disagree with the
truth, and it disagrees in the way that costs a customer. A customer
told to confirm an address they had already confirmed is a customer
who gives up, and the local copy was false in exactly that case for
as long as the provider's message was in flight.

So the rule is now: **the provider proves the address, and the
application does not keep a copy of the answer.** The upload gate and
the banner are gone with it, and the upload is refused for the
reasons that are still this application's business: the file, the
price, the state of the order.

The address itself is still on the account, because the order is tied
to it and a human has to read it. It is read from the provider's own
API when the account is made, and not from the browser.

### The one question, and the one place the role is decided

A person who signs in has proved who they are and has not yet said
what they are here for. Those are two different states, and the
application has four rather than three: loading, signed out, signed
in without an account, and signed in with one.

The account is made in exactly one place, the onboarding, where the
person says whether they are here to print something or to run a shop.
The role is read from the database and never from the token, because a
token is something the caller presents and a role is a thing the
application decides. The role is chosen once and never changes, which
is the rule that was already in place.

The onboarding reads the address and the name from the provider rather
than from the body, because the provider proved them and the browser
did not. The body carries the intent and nothing else.

### The provider's API is behind a bot protection

Clerk's backend API refuses a request with no user agent of its own,
and the one the Python standard library sends by default is refused.
The request names the application instead. It is a small thing, and it
cost an afternoon to find, and it would cost anyone else who reads one
of the provider's answers the same afternoon.

The provider's public keys are published at a fixed address and its
script is loaded from its own host, so the content security policy has
to allow that host. It is read from the environment rather than
written into the policy, because a policy that allows the wrong host
is a policy that does not mean anything.

### The free tier, and what it costs

The facts below were checked against Clerk's own documentation and
pricing on 2026-10-21, and are recorded here because a plan that
depends on a provider's tiers has to name what it is relying on.

What the free tier includes, and what this project uses: sign-up and
sign-in, password sign-in, **email verification with "verify at sign
up" on by default**, email codes and email links, **up to three social
connections** (Google, GitHub, Facebook), webhooks for data sync,
sign-in tokens, automatic account linking, user metadata, account
lockout and brute force protection, restricted access, disposable email
and subaddress blocking, 50,000 monthly retained users per application,
unlimited applications and three dashboard seats.

Two things on the free tier cost something real, and both are accepted
in writing rather than discovered later:

1. **The verification email and the sign-in screen carry Clerk's
   branding**, and on the free tier the template cannot be edited and
   the branding cannot be removed. This replaces a hand written
   "Confirm your email address" message. For a portfolio project this
   is a visible polish regression. The trigger to revisit is the Pro
   plan, and a paid plan is not in scope now.
2. **A development instance delivers at most 100 Clerk emails a
   calendar month**, after which one time code requests are refused.
   The local stack never needs a real email, and the test mode
   addresses settle the rest.

What the free tier does not have, and what this project therefore does
not promise: multi factor authentication, passkeys, custom email
templates, custom password requirements, a custom session lifetime
(the free tier's is fixed at seven days, which happens to match this
application's refresh token), and removal of the Clerk branding.

### One more thing the free tier changes: the token is short lived

A Clerk session token lives about sixty seconds, and the frontend SDK
refreshes it in the background. This application issued fifteen minute
access tokens, so the frontend has to ask Clerk for a token per
request rather than hold one. The token stays in memory and is never
written to `localStorage` or `sessionStorage`.

The token is also thinner than this application's was. Clerk's default
session token carries the subject, the issuer, the origin and the
times, and **not** the email address and **not** an audience. The
backend therefore checks the issuer, the origin, the expiry and the
subject, and the email address is read from the local row, which the
webhook keeps in step.

## Alternatives considered

1. **Keep the hand written authentication.** Rejected, and this was the
   default position until the owner decided otherwise. The
   authentication works and it is well tested. The reasons to move are
   that password hashing and token rotation are solved problems that
   this project should not be spending its interview time on, and that
   the free tier's limits are far above what a college print shop
   needs. The cost of the decision is real and is named above: the
   thing being demonstrated changes.
2. **Clerk, but keep this application's own sessions.** Rejected: it
   would mean keeping the password hashes, the refresh tokens and the
   rotation, and adding Clerk on top, so the code would grow rather
   than shrink.
3. **Clerk's Organizations and Clerk-hosted authorization.** Rejected:
   they would put the role and the shop in Clerk, and the role is the
   thing this project wants to own, because the ownership rules are
   the demonstration. A vendor's shop is a row in this database with a
   foreign key, and the authorization matrix in the backend structure
   document stays exactly as it is.
4. **Clerk's official Python SDK.** Rejected: it disables issuer
   verification (`verify_iss: False`), and it pulls in `httpx` and
   `pydantic` for a wrapper around a JWT verification that `pyjwt`
   already does. The verification here is written directly, so that the
   issuer check, the origin check and the key rotation behaviour are
   all visible in this repository and all testable offline.
5. **A paid Clerk plan.** Rejected for now: the free tier covers
   everything this project uses, and the two costs it carries (the
   branding and the development email cap) do not justify a paid plan
   for a portfolio project. Both are named in this document so that the
   decision is revisited on purpose rather than by accident.
6. **Point Clerk's email at Brevo.** Not possible, and the reason is
   the rule above: the verification link is a token only Clerk can
   validate.

## Consequences

- The dependency count goes up by one on the backend (`cryptography`,
   which `pyjwt` needs to verify an RSA signature and which is not
   present today) and by one on the frontend (`@clerk/react`). The
   official Clerk SDK is not used, and neither is `httpx` at runtime.
- This application stops issuing tokens, stops hashing passwords, and
   stops sending verification emails. The refresh token table and the
   email verification token table go, each in its own migration, in the
   contraction phase, after the cutover has been verified. The OAuth
   identity table and the OAuth gateway have already gone: they were
   removed with [ADR 027](027-sign-in-with-google-without-a-new-dependency.md),
   because Clerk's own social connections replace them.
- **The `JWT_SECRET` setting is gone, and the local access token
  machinery with it.** The setting is not kept for the sake of a
  rollback, because a rollback to the previous image is a redeploy and
  the previous image brings its own settings with it. The password
  column stays, nullable, and is dropped in the contraction, because
  the deployment runs the migrations before the new image starts and a
  migration that removed a column the previous image still reads would
  break that rollback.
- **The local way in is a route, not a flag in the product.** The end
  to end suite has to run offline and the same way every time, so it
  signs in through a route that mints a session without the provider,
  through the same interface the real verifier is read through. The
  setting that turns it on is refused in production, and the
  application refuses to start without the provider's settings, so a
  deployment cannot run with the front door open.
- The authorization matrix, the ownership filters, the 404 on cross
   tenant access, the money rules and the file privacy rules are
   untouched. The tests for them are the tests for this change.
- The customer now gets a Clerk branded verification email and a Clerk
   branded sign-in screen. This is the visible cost of the free tier.
- This application becomes dependent on a hosted service for signing
   in. A Clerk outage does not take the service down, because the
   public keys are cached and a request is only refused when the
   token cannot be verified at all, but new sign-ups do stop working
   while Clerk is down.
- The role is fixed at onboarding, so a customer who later decides to
   run a shop needs a separate account. This matches today's
   behaviour, where the role is a single value with no promotion path.
- The DNS for this project's domain needs Clerk's SPF and DKIM records.
  If Brevo also sends from the domain, the SPF record holds both
  mechanisms and the two DKIM selectors are separate. This is one
  deliberate change, not two.
- **The sign-up form asks for an email and a name, and nothing else.**
  A new Clerk instance requires a phone number at sign-up, and Clerk
  does not support Indian (+91) phone numbers, so left alone **no
  Indian customer could register at all**. The phone number is
  therefore optional, and not used for sign-up. It stays enabled as a
  second factor, which is the one thing it could still be used for,
  though that is a paid plan feature for production use and it has
  the same country limitation, so multi factor authentication is not
  available to this product on the free tier.
- Clerk's own password rules apply once it owns the password: a
  minimum of 15 characters, and a check against a list of breached
  passwords at sign-in, which is a call to a third party and a
  network dependency the test suite has to know about.

## The smoke test, walked by hand on 2026-10-21

The test suite never reaches the provider, so the cutover was proved
against the real one by hand, in a browser, on the development
instance.

What was walked, and what was seen:

1. The landing page loads.
2. The sign in page shows the provider's own card, with the Google
   connection offered, and the "Secured by Clerk" branding that the
   free tier costs.
3. The address, then the password, then the code. The code is asked for
   because the provider does not know that device, and `424242` proves
   an address whose name ends in `+clerk_test`.
4. The application calls `GET /me` and is answered `403` with
   `ACCOUNT_NOT_PROVISIONED`, which is the state between signing in and
   choosing.
5. The onboarding page asks the one question, and answering it creates
   the account: `spn-check+clerk_test@example.com`, role `customer`,
   the provider's identifier `user_3L0f8DSMjlcFb2PGS4Jhc1taqYQ`, and
   the name the provider holds.
6. The application then answers `/me` with `200`, and the header shows
   the address and a sign out.

Two things were found by walking it that no test would have found.

The provider's API refuses a request with no user agent of its own,
and the one the standard library sends by default is refused. The
request names the application now.

The application decided that a person was signed out before the
provider had finished loading, because "not signed in" and "not looked
yet" are two different answers and the application believed the first
one too early. A person who had just signed in was sent back to the
sign in page. The session now waits for the provider.

## The deployment on the home server, 2026-10-22

The cutover was put on the home server, behind the quick tunnel, and
walked by hand. Four things were found there that the local
environment could not have shown, and all four are now in the
repository.

**The provider's fraud protection is a widget in the page, and the
content security policy has to allow it to run.** The widget is
Cloudflare's, it runs in the page, and it does two things the policy
has to allow: it evaluates the code it is given, and it fetches an
empty address to see whether the page is allowed to fetch at all.
Without them the widget cannot start, the check it exists for never
finishes, and nobody can create an account. The empty address reaches
no host.

**The sign in has a step after the password.** The provider asks for a
code when it sees a device it has not seen, and the code goes to the
address. An account whose address is not a real inbox cannot receive
it, so the provider's address for those accounts is a test one, whose
code is always the same, and the local account keeps the address it
had.

**An account that existed before the provider did has no identity in
it.** The provider does not know those people and the application has
no password to check, so they cannot sign in at all. A script gives
each of them an identity and records the provider's identifier on the
local row. The passwords are made there and printed once.

**A person who signs in lands on the front page, which is a page for
people who are not signed in.** A person who has signed in and has no
account can do nothing until they have said what they are here for,
so they are asked the one question first.

The home server's own deployment settings were on the box and not in
the repository: the ports it binds, the networks whose forwarded
headers it believes, and the image and platform of its database. They
are in the repository now, and the box pulls them like everything else.

## Revisit if

- The plan changes, or the application needs multi factor
  authentication, passkeys or a branded verification email.
- The customer base grows past the free tier's monthly retained user
  allowance, or the dashboard seat limit of three becomes a problem.
- Safari's ITP ends sessions too often on the shared Clerk domain, in
  which case the answer is a custom domain or a proxied Frontend API,
  and both are configuration rather than code.
- The notification backlog is picked up, at which point Brevo is
  configured against the `SMTP_*` settings and the `EmailSender`
  interface, and the first product email is sent through it.
- Clerk changes the session token's claims or the webhook's signature
  scheme, which the verifier and the webhook handler would have to
  follow.
