# ADR 026: The email address has to be proved

Date: 2026-10-20
Status: Accepted, superseded in part by [ADR 029](029-clerk-authentication-with-local-authorization.md)
Requirement: FR-19 (Sprint 5.7, hardening)

> **Superseded in part (2026-10-21).** The *rule* in this record is
> unchanged and is the important half of it: an address is a claim
> until it is proved, and an unproved account cannot order a print,
> because the printout and the pickup code are tied to the address.
> What changed is who sends the link and who stores the token. After
> the authentication provider migration, Clerk sends the message and
> proves the address, and this application keeps a copy of the answer
> in `users.email_verified`, updated by a signed webhook. The local
> `EmailSender` interface stays in the codebase for the product email
> that the notification backlog will need. See
> [ADR 029](029-clerk-authentication-with-local-authorization.md).

## Context

The email address of an account was a claim and nothing more. It was
never proved, and there was no way to prove it, because there was no
mail in the platform and no way to change the address either.

Three things follow from that, and all three are bad.

A customer who typed their address wrong could not recover. The account
was made, the address was taken, and the account could never do
anything, because the address it held was not theirs. There was no
password reset and no change of address, so the only way out was for
the operator to delete the row, and the address was gone with it.

Somebody could claim anybody's address. `victim@example.com` was one
registration away from being taken, and the first person to register it
owned it. The platform did not send any mail, so nothing was stolen
yet, but that was a property of the platform and not a decision: the
moment a message is sent to the address on an account, the person who
claimed it starts receiving it.

Nobody had to be a person to make an account. Every registration was a
row, and the registration limits in
[ADR 025](025-the-limits-on-creating-an-account.md) bound how many of
them there could be, but not whether any of them was real.

The address was also the only name the platform had for a customer. It
is shown next to an order and in the vendor's queue, so it is worth
something.

## Decision

An account has to prove its address before it can order a print.

**The proof is a link.** A token is made, its hash is stored, and a
message with a link that carries the token is sent to the address. The
link is opened, the token is proved, and the account is marked as
proved. The token is stored as a hash, the way a refresh token is, so a
row that is read from the database cannot be turned into a link that
proves anything.

**The link is sent by a gateway, not by the application.** There is an
`EmailSender` interface with three implementations: SMTP, which is the
standard library doing it, a console sender that writes the message to
the log for a local machine, and a memory sender for the tests. The
console sender is refused when the environment is production, because
the link in a message is a secret and the log is where secrets go to
leak.

**The account still works.** An account that has not proved its address
can sign in, look around and change its address. What it cannot do is
upload a file or order a print. That is the whole of the restriction,
and it is on the two actions that need a real address: the printout and
the pickup code are tied to it.

**The address can be changed, with the password.** This is the way out
of a mistyped address, and without it the proof is only a way to find
out that an account is broken. The new address is unproved until it is
proved in turn, because the old one was never proved. The password is
asked for, because changing the address is how an account is taken
over, and a session that was stolen is not the password.

**The operator can prove an address without sending anything.** The
`verify-email` command marks an account as proved, for the demo
accounts and for a customer who cannot receive mail at the address they
gave. It is the same decision the shop verification makes: the person
who holds the server decides.

The expired tokens are deleted by a job, because a token is a secret
until it is used and the ones that are never used are the ones that
were sent to an address nobody reads.

## Alternatives considered

1. **Leave the address unproved and keep the limits.** Rejected. It
   bounds the number of accounts and says nothing about whether any of
   them is a person. The problem the platform has is not the number of
   accounts, it is that a claim and a fact look the same.
2. **Prove the address and block the whole account until it is proved.**
   Rejected. A customer whose mail is slow, or whose address is a
   typo, would be locked out of an account they can sign in to, with
   nothing to do about it. The account works; the one thing that needs
   a real address does not.
3. **Check the domain of the address instead of proving it.** Rejected
   as a defence. A lookup says the domain exists, not that the person
   who gave the address can read mail at it. It also costs a network
   round trip on the path that creates accounts, and it says nothing
   about an address at a domain that does exist.
4. **Send the whole notification system as well.** Rejected as scope.
   The platform sends one message, a link, and it sends it because the
   link is the proof. Order receipts and status messages are a
   different feature, and they are still in the parking lot.
5. **Use OAuth instead of a link.** Rejected for now, and it is not
   really an alternative: a sign in with Google proves the address in
   exactly the same way, through a provider that says it. The link is
   the same idea with fewer parts, and it works for an address that
   has no Google account. The two can sit next to each other later, and
   the table that holds them is the same shape either way.

   *(Updated 2026-10-21. The two do now sit next to each other, in the
   other order: the identity provider sends the verification message
   and proves the address, and this application keeps a copy of the
   answer. The hand written OAuth client that the alternative referred
   to has been removed. See
   [ADR 029](029-clerk-authentication-with-local-authorization.md).)*

## Consequences

- A customer can order a print only after the address is proved, and a
  customer who typed the address wrong can put the right one there.
- The platform knows which addresses are real, which is what a message
  to a customer needs, and it does not yet send any.
- A deployment needs an SMTP server, or it cannot prove an address.
  The console sender is refused in production, so a deployment that
  forgets is refused at startup rather than quietly writing links to
  the log.
- The address is no longer only a login name. It is a claim until it
  is proved, and the platform says so.
- A customer whose mail does not arrive has one thing to do: sign in
  and ask for the link again, or change the address. Both are on the
  screen.
- The tokens expire after a day, and the expired ones are deleted by
  the worker.
