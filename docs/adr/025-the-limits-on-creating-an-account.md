# ADR 025: The limits on creating an account

Date: 2026-10-20
Status: Accepted
Requirement: FR-1 (Sprint 5.6, hardening)

## Context

Registering was limited to five registrations a minute from one address,
and that was all. A machine that wanted an account every twelve seconds
would get one, for as long as it liked, and so would a thousand
machines aimed at the same deployment.

Two things make that more than a nuisance.

The first is the cost. Creating an account hashes the password with
argon2id, which takes about twenty milliseconds of CPU that the server
cannot refuse once it has started it. Five registrations a minute from
one address is nothing. Five registrations a minute from a thousand
addresses is a hundred and sixty seconds of CPU a minute, which is more
than one core, spent on nothing but password hashes.

The second is what the accounts are for. An address that nobody has
claimed can be claimed by anybody, and the first one to claim it owns
it. A machine that sprays one address from a thousand addresses gets the
address, and the person it belongs to is the one who is refused.

The limits that already existed were also keyed in the wrong place for
the second problem. Every one of them was keyed on the address of the
machine, so many machines could do together what one machine could not.

## Decision

Four limits on `POST /auth/register` and `POST /auth/register-vendor`,
each for a different way the work can be asked for too many times.

| Limit | Key | Default | What it stops |
|---|---|---|---|
| Per address, per minute | the address of the machine | 5 | One machine asking for many accounts at once |
| Per address, per day | the address of the machine | 100 | One machine asking for a slow drip, which the minute limit does not see |
| Per account, per hour | the email address | 5 | Many machines claiming the same address |
| Per process, per minute | nothing: the whole deployment | 60 | The deployment spending its CPU on password hashes |

The last one is the one that answers the question "can a botnet crash
the web by registering". It does not care how many machines are
involved: the deployment creates at most sixty accounts a minute, and
the work is bounded whatever the attacker does.

The per address limits are generous, and that is deliberate. A campus
puts every student behind one address, so a limit that rations signups
locks out the people it is meant to serve. The same reasoning is in
[ADR 019](019-rate-limiting-a-login-per-account.md), where a limit on
logins was widened for the same reason. A hundred a day is more than
any one address needs and less than a drip.

The account key is the account the database resolves, and an address
that resolves to no account is keyed by a hash of the address itself.
The same rule is used for the login limits, so two spellings of one
address cannot occupy two buckets.

The limits are settings, because a deployment knows its traffic and this
project does not: `REGISTER_ADDRESS_PER_MINUTE`, `REGISTER_ADDRESS_PER_DAY`,
`REGISTER_ACCOUNT_PER_HOUR`, `REGISTER_GLOBAL_PER_MINUTE`.

Accounts that were made and never used are a separate problem, and they
are handled by the operator rather than by a job. `prune-unused-accounts`
lists the customer accounts that have no order, no upload and no session
since they were created, and deactivates them only when it is asked to
with `--apply`. A deactivated account keeps its address, so the address
cannot be claimed by somebody else, and `activate-account` gives it
back. Nothing is deleted, because a customer who signed up last week
and has not printed anything yet looks exactly like an account nobody
wants.

## Alternatives considered

1. **One limit, the one that exists.** Rejected. It bounds one machine
   and says nothing about a thousand of them.
2. **A captcha on the registration form.** Rejected. It is a new
   dependency, it is a bad experience for a student on a phone, and it
   pushes the work onto the person rather than onto the machine that
   is doing it.
3. **Check the domain of the address before creating the account.**
   Rejected as a defence. A domain lookup says the domain exists, not
   that the person who gave the address can read mail at it, and it
   costs a network round trip on the path that creates accounts. It
   does not replace verification, and verification is not in this
   change.
4. **Delete the unused accounts instead of deactivating them.** Rejected.
   A deleted row releases the address, and the next person to claim it
   gets an account that looks like the old one. Deactivating keeps the
   address spoken for, which is the thing that was worth protecting.
5. **Let the job deactivate the unused accounts on a schedule.**
   Rejected. The same shape covers a real customer who has not printed
   anything yet, and a job that closes accounts nobody looked at is a
   job that closes real accounts. The operator decides.

## Consequences

- A machine can create at most five accounts a minute and a hundred a
  day from one address, and a deployment can create at most sixty a
  minute in total. The last number is the one that bounds the CPU.
- An address can be claimed five times an hour from anywhere, so
  claiming somebody else's address is no longer a matter of having
  enough machines.
- The limits live in the process, like the other limits, and are reset
  when it restarts. That is the documented limit of the single instance
  deployment, unchanged from
  [ADR 012](012-in-memory-rate-limiter.md).
- A deployment under a flood of registrations refuses new signups with
  a 429 and a message that says the server is busy. That is a real
  trade: the work is bounded, and the people who are refused during
  the flood are the people the flood is aimed at.
- The operator can see the accounts that were made and never used, and
  can close them without losing the addresses.
