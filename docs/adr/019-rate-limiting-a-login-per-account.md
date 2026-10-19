# ADR 019: Rate limiting a login per account and per address

Date: 2026-10-20
Status: Accepted
Requirement: FR-1 (Sprint 6)

## Context

The login endpoint was rate limited to ten attempts a minute, keyed by
the address the request came from.

That number is right for one customer and wrong for the real user. A
college puts every student behind one address. A campus of a few hundred
students shares a single public IP, and the limit applies to all of
them together. Ten logins a minute for a whole campus means that at
9am, when a class of sixty students all decide to print their
assignments, some of them cannot sign in. The rate limiter would be
locking out paying customers to defend against an attack that is not
happening.

The limit is also the wrong shape for the attack it is meant to stop. An
attacker guessing one password wants many attempts against *one*
account. Keying on the address alone stops that only by accident: the
attacker has to be sharing an address with other people, or has to give
up before ten tries, which is a low bar.

The end-to-end suite found this. It signs in a handful of times, all
from one address, and it was refused.

## Decision

Count a login attempt twice, against two different keys:

- **the account**: ten attempts a minute for one email address. This is
  the brute force limit, and it is exactly as strict as before for the
  attack it exists to stop.
- **the address**: forty attempts a minute for one address. This is the
  credential stuffing limit: a machine spraying many accounts from one
  place is stopped, but a campus full of students is not.

Both are checked on every attempt, and either one being used up refuses
the request with `RATE_LIMITED` and a `Retry-After` header.

The account key is the email from the request body, lowercased. The
body is read from the request's cache, which FastAPI has already filled
by the time the dependency runs, so nothing is read from the stream
twice.

## Alternatives considered

1. **Raise the per-address limit and leave it there.** Rejected: it
   helps the campus and does nothing for the account. A brute force
   against one account from a dedicated machine would then be allowed
   forty guesses a minute, which is a weaker guarantee than the one the
   code has today.
2. **Count only failed attempts.** Rejected as a larger change: the
   successful attempts are what the campus problem is made of, so the
   limit has to count them, and counting only failures would let an
   attacker lock a real customer out of their own account.
3. **Per account only, with no address limit.** Rejected: credential
   stuffing against many accounts from one machine would be unlimited.
4. **Leave the limit alone and make the test suite sign in less.** This
   was tried first and it does not work: the suite is not the only
   thing that shares an address, and the campus case is real. It also
   would have left the brute force limit exactly as coarse as it is
   now.

## Consequences

- The limiter has one more kind of key. The existing `RateLimiter` was
  already generic over the key, so this is a new function rather than a
  change to the limiter itself.
- A customer behind a shared address is no longer refused for signing
  in. A brute force against one account is refused at the same rate as
  before.
- The end-to-end suite signs in several times from one address and is
  no longer refused, which is what made the problem visible.
- The rate limiter still lives in the process, so a second API instance
  would need a shared one. That limit is unchanged and still documented
  in ADR 012.
