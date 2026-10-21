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
- The `JWT_SECRET` setting stays until the local access token machinery
   is removed. It used to sign the OAuth state cookie as well, and that
   reason no longer applies, but the access token is still signed with
   it.
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
