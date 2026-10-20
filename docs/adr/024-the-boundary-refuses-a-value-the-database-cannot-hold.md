# ADR 024: The boundary refuses a value the database cannot hold

Date: 2026-10-20
Status: Accepted
Requirement: FR-1 (Sprint 5.6, hardening)

## Context

A customer could type an address with a NUL byte in it. The shape of the
address was checked, so the NUL was accepted, and the insert then failed
with `psycopg.DataError: PostgreSQL text fields cannot contain NUL
(0x00) bytes`. The customer saw a 500, the log held a stack trace, and
the answer carried no request id, so the failure could not be tied to
the request that caused it.

The same happened with a NUL in a name, a shop name, a shop address, a
rejection reason, or the name of an uploaded file. The login route was
the worst of them: the address was used to look the account up inside
the rate limit dependency, so the failure happened before the attempt
was even counted, and one address could produce unlimited 500s.

The shape of a value and whether the database can store it are two
different questions, and only the first one was being asked. A NUL is
not the only character with the problem, but it is the one that reaches
the database, because PostgreSQL's `text` cannot hold it.

A second thing went wrong with the 500. `RequestIdMiddleware` holds the
request id in a context variable, and it unwinds that variable when it
returns. An unhandled exception is answered by a handler that sits
outside the middleware, so by the time the answer was built the id was
gone: the body said `"request_id": ""` and no `X-Request-Id` header was
sent. The 422 answers had an id. The 500s, the ones worth looking at,
did not.

## Decision

Three changes, in the order they matter.

1. **The boundary asks the second question.** Every string that is
   written to the database is checked by `app/schemas/text.py` before it
   is passed on. The rule is: no control characters, and no bidi
   override characters. Tab and newline are allowed where the field is
   genuinely more than one line, such as a shop address. The zero width
   characters that real scripts use are left alone, because those are
   letters rather than tricks. The rule is applied to the email as
   well, to the name, the shop name, the shop address, the rejection
   reason and the name of an uploaded file.

2. **A value the database refuses is a 422, not a 500.** The error
   handler answers a `DataError` with `VALIDATION_ERROR`, which is what
   it is: the request carried a value the caller has to fix. This is
   the net under the boundary, for the field somebody forgets to
   annotate. The log line says `database_rejected_value` so that a
   pattern of them is visible.

3. **A 500 names the request it came from.** The request id is kept in
   the request scope as well as in the context variable, and the error
   handler reads it from there. The answer carries the id in the body
   and in the `X-Request-Id` header, whatever the failure was.

The webhook payload is stored with any NUL byte taken out of it, because
the inbox row is written before the payment is applied: a payload that
cannot be stored would stop a payment from being applied at all. The
decision is still made from the payload as it arrived.

## Alternatives considered

1. **Catch the error in the services that write to the database.**
   Rejected as incomplete. It would have fixed the registration path
   and left the shop update, the rejection reason and the upload name
   to be found one bug at a time. The boundary is the one place every
   value passes through.
2. **Store the value anyway, with the NUL escaped.** Rejected. The
   value is a login name and a display name; an escaped one would be
   shown to people, compared against other accounts and used as a key.
   A value that cannot be stored is a value to refuse.
3. **Leave the 500 alone and let the logs carry it.** Rejected. A 500
   caused by a keystroke is a wrong answer, and an answer nobody can
   correlate with a request is an answer nobody can act on.
4. **Strip the control characters instead of refusing them.** Rejected.
   Silently changing what somebody typed is worse than telling them it
   will not do, and a name that arrives different from the one that was
   typed is a name that cannot be trusted.

## Consequences

- A NUL byte in any of these fields is a 422 with a message that says
  what to fix, not a 500 with a stack trace.
- A name that contains a character which reverses how it is displayed is
  refused. That is a deliberate refusal: such a name can be made to
  read as a different one.
- The published OpenAPI schema is unchanged. The rule is a validator, so
  the contract still says `type: string`, and the contract fuzzer still
  agrees with the server.
- The `email-validator` package is still declared in
  `pyproject.toml` and still used by nothing. It is the obvious way to
  make the address rule stricter, but a stricter rule would refuse
  addresses the published `format: email` allows, and the fuzzer proved
  that the two have to agree.
- A 500 now carries the request id, so the log line and the answer can
  be put next to each other.
