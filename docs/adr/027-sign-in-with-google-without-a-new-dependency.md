# ADR 027: Sign in with Google, without a new dependency

Date: 2026-10-20
Status: Accepted
Requirement: FR-20 (Sprint 5.8, hardening)

## Context

The customer and the shop owner both have to make an account, and
making an account is a form, a password to remember, and an address to
type. Every one of those three is a chance to get it wrong, and the
address in particular is the one the platform has just started to
prove.

Google accounts are already a thing people have. Signing in with one
takes the password away, and it brings an address that has already been
proved by somebody else, which is the thing the platform has just built
a whole mechanism for.

The obvious library for this is Authlib. It is the standard OAuth and
OIDC client for Python, it is maintained, and it is MIT licensed. It
is also the wrong shape for this project.

Authlib 1.9 pulls in `cryptography` (a native wheel, three and a half
megabytes) and `joserfc` (a JOSE library). This application uses
neither. It never validates an id token: it asks the provider's
userinfo endpoint over TLS with a server-to-server access token, and
reads the claims from the answer. The whole of the cryptography in
OAuth is about signing and verifying tokens, and the part this
application uses does not sign or verify anything.

The other thing to weigh is the flow itself. It is small. There is an
authorization URL to build, a code to exchange for a token, and a
profile to fetch. The fiddly parts are the state, the PKCE verifier
and its challenge, and not putting the token in a log. That is a
hundred lines of code that anybody can read.

## Decision

The OAuth client is written with the standard library, and it is behind
an interface, so the provider is a detail.

**The provider is an interface.** `OAuthProvider` has two methods: the
authorization URL to send a browser to, and the exchange of a code for
a profile. There is one real implementation (Google) and one fake for
the tests. The application never sees an OAuth URL, a token or a
scope.

**The flow is the authorization code flow with PKCE, and no id token.**

1. The front end asks the server to start. The server makes a state
   and a code verifier, keeps them in a signed cookie that lives ten
   minutes, and answers with the address to open. The state and the
   verifier are the only things that are kept, and they are kept
   client side, signed, so there is no table of half finished logins.
2. Google sends the browser back with a code and the state. The server
   checks the state against the cookie, and refuses the request if it
   does not match. That is what stops a third party from starting a
   sign in and having the browser land on somebody else's account.
3. The server exchanges the code for a token, proving itself with the
   verifier from the cookie. PKCE means a code that was intercepted
   cannot be used without the verifier, which never left the server.
4. The server asks the userinfo endpoint who the account belongs to,
   and reads three things: the identifier of the account at the
   provider, the address, and whether the provider says the address is
   proved.
5. The server finds the identity by the provider and the identifier.
   If it is there, the account is signed in. If it is not and the
   address is free, the account is made, with the address proved
   because the provider says so. If it is not and the address is
   taken, the request is refused: see below.

**An identity is never linked by the address alone.** The address is
what the provider says it is, and the provider says it about *an*
account, not about *this* platform's account. If the address is
already in the platform, the sign in is refused and the customer is
told to sign in with their password and connect the provider from
their account. The other way round is how accounts are taken over: a
platform that links by address lets whoever claimed the address first
own the account of whoever the provider vouches for.

**The tokens of the provider are not kept.** The platform needs to
know who the customer is, and that is what the identity row is for. The
access token and the refresh token of the provider are used once and
discarded, so there is no provider secret in the database and nothing
to revoke there.

**The sign in happens the ordinary way.** The callback issues the same
tokens as the login does and sets the same refresh cookie, and then
sends the browser to the front end. The front end asks who it is, as
it does after any sign in.

## Alternatives considered

1. **Authlib.** Rejected, and the reason is in the context: it brings
   `cryptography` and `joserfc` for a flow that uses neither, because
   this application never validates a signed token. It would be the
   right choice if the application consumed id tokens, and the
   difference is one line of scope. The cost is a native dependency in
   the image and a hundred lines of code nobody in the project has
   read.
2. **Validate the id token instead of asking the userinfo endpoint.**
   Rejected. It is the tidier OAuth, and it needs the signed token
   machinery that Authlib brings, which is what the previous alternative
   was rejected for. The userinfo endpoint says the same three things
   over a connection the server authenticates.
3. **Link an account by the address when the provider says the address
   is proved.** Rejected, and it is the important one. A platform that
   has just started to care about who owns an address cannot then let
   a proved address from somewhere else take over an account that was
   claimed here. The safe rule is the boring one: the provider proves
   the address, and the platform proves that the person asking is the
   one who made the account.
4. **Keep the provider's access token, to ask the provider again
   later.** Rejected. Nothing in the product needs it, and a stored
   refresh token is a secret with a life of its own. The identity row
   says everything the platform needs.
5. **Apple as well as Google.** Rejected for now. Apple needs a paid
   developer account and a domain, and the project has neither. The
   provider is behind an interface, so adding one is a file and a
   setting.

## Consequences

- A customer can sign in with a Google account and never make a
  password. The address is proved by the provider, so the account can
  order a print at once.
- An account that was made with a password keeps working exactly as
  before. A customer who already has one signs in with their password
  and connects Google from their account, and the connection is only
  made when the person asking is the owner of the account.
- A customer whose address is already taken by an account here cannot
  sign in with Google, and is told why. It is the price of not letting
  one person take over another person's account.
- The platform stores no provider secret. The client id and the client
  secret are configuration, and the client secret is only ever used in
  the token exchange.
- There is no new dependency, and the OAuth client is a file the owner
  can read line by line.
- The flow is tested against a fake provider, so the test suite needs
  no network and no Google account.
