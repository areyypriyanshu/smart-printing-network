# ADR 031: The free geocoder is the default, and the rules that come with it

Date: 2026-10-22
Status: Accepted
Requirement: Phase 2, FR-22 (sprint 7)

## Context

Sprint 7 built the shop search with a geocoding provider behind an
interface, and the first provider was Google. Google now asks for a
billing account before it gives out a key, and the owner does not want
a bill for a portfolio project with a handful of shops.

The free alternatives are not all equal, and the two serious ones are
run on donated servers with usage policies that are not optional.

**Nominatim**, the geocoder of the OpenStreetMap Foundation, is free,
needs no key and no account. Its
[usage policy](https://operations.osmfoundation.org/policies/nominatim/)
asks for four things, and forbids three:

- no more than **one request a second**, and the limit is on the whole
  application rather than on one customer;
- a **User-Agent that identifies the application** — "stock User-Agents
  as set by http libraries will not do" — and a way to reach the
  operator;
- the **attribution displayed** wherever the data is displayed, and the
  data is under the ODbL, so share-alike;
- the answers **cached** on our side;
- **client-side autocomplete is forbidden**: "you must not implement
  such a service on the client side using the API";
- the service must be **swappable without a software update**, and the
  policy asks for a proxy in front of it;
- **no reselling** of the results, and an application whose primary
  function is geocoding must run its own.

**Photon**, from Komoot, is also free, needs no key, and is Apache-2.0.
Its demo server asks for "a reasonable limit" and gives no availability
guarantee. Self-hosting it wants 64 GB of RAM and about 95 GB of disk
for the planet, so it does not fit on the home server.

## Decision

**The free provider is the default, and the paid one is a setting away.**

`GEOCODING_PROVIDER` is `nominatim`, `google` or `none`. It is
`nominatim` by default, so a fresh checkout can look an address up
with no key, no account and no bill. `google` is for a deployment that
has a key and wants the better matching of an Indian address.
`none` is for a deployment that would rather not depend on a donated
service at all: the shop owner types the coordinates and the customer
who will not share a location sees the whole list.

**The four rules the policy asks for are kept, in the code, and each one
has a test:**

1. **One call a second for the whole application.** A `Throttle` sits
   in front of the call, on the process and not on a customer, and it
   holds the lock while it waits so that two customers asking at the
   same moment take turns instead of both going out.
2. **A User-Agent that says who is asking.** The default names the
   application and points at the repository, which is where the
   operator can be found.
3. **The answers are cached.** A `CachedGeocoder` keeps an hour of
   answers in the process, including the answers that were "no such
   place", because asking again would ask the same question.
4. **The attribution is shown.** The provider carries the attribution
   it asks for, the responses carry it, and the customer-facing pages
   show it. It is shown with the list of shops and with the search
   results, which are the places where a shop's place on the map is
   shown to a person.

**The proxy is the application itself.** The browser never asks the
provider. It asks this server, which asks the provider with the
server's own user agent. That is what the policy asks for, and it is
also why the provider can be changed with a setting and a restart.

**There is no autocomplete.** The search box is a box and a button,
and the address goes out when the person says so. This was found by
review, not by design: the first version sent the address as it was
typed, which made one lookup per keystroke, and that is exactly the
autocomplete the policy forbids. It is also what the first version of
this document claimed did not exist, which is the reason to write down
what the code does rather than what it was meant to do.

The review also found three things that had to be fixed before the
policy could be said to be kept, and they are here now:

- **The lookup happens outside the database transaction.** The address
  is looked up before the connection is taken from the pool, because a
  call to somebody else's server can take ten seconds and the pool is
  small.
- **Two people asking for the same address make one call between
  them.** The policy says that "clients sending repeatedly the same
  query may be classified as faulty and blocked", so the second
  caller waits for the first answer.
- **The rules are wired into the geocoder the application builds, and
  that is tested.** A test that only exercised the throttle on its own
  would still pass if the throttle were left out of the built
  geocoder, and then every call would go out at once.

**The rate of a page has a ceiling, and it is not arbitrary.** The
price of an order is pages x copies x rate, the largest order the
platform takes is 300 pages of 100 copies, and the column that holds
the price is a 32 bit integer. A rate of more than fifty thousand
paise would let a shop price an order the database cannot hold, and
the failure would land on the customer who tried to order, not on the
shop that set the rate. The ceiling is at the boundary, on both sides
of it, and the database check that already existed is left alone: a
migration that narrows a constraint would stop the previous version of
the application from writing a rate it used to allow, which is the
thing that breaks a rollback.

**The price the search shows is worked out in Python, and only the
order is worked out in the database.** The order of the shops by
price needs the database to do the arithmetic, and that arithmetic is
cast to a wide integer first: the rate column is a 32 bit integer, and
so is the product, and a large enough rate would overflow it. The
overflow was found by review too. It broke the search for every
customer because of one shop's rate, and the answer blamed the
customer.

**The shop's own coordinates still come first, and now the browser can
supply them.** A shop owner is standing in their shop when they
register, so the registration form has a "Use my current location"
button. It is exact, it is free, and it needs no provider at all. The
typed coordinates and the address lookup are the fallbacks.

**The free provider matches loosely, and the product says so.** Asking
the public instance for "Kolkata Salt Lake Sector V 999999" returns
the nearest place it knows, which is Salt Lake. That is how a fuzzy
matcher behaves, and it is why the shop owner's own coordinates are
the first choice and not the last.

## Alternatives considered

1. **Keep Google and add a billing account.** Rejected for now: the
   usage at this scale would cost nothing, but it asks for a card and
   it puts a bill-shaped shadow over a portfolio project. It remains
   one setting away, and it is the better matcher for an Indian
   address.
2. **Photon instead of Nominatim.** Rejected for now: it does
   search-as-you-type and tolerates typos, which is nicer, but its
   policy is vaguer ("a reasonable limit") and self-hosting it does
   not fit on the home server. The gateway is an interface, so it is
   one file and one setting away as well.
3. **Run our own Nominatim.** Rejected for now: a country extract
   wants about 8 GB of RAM on its own, and the home server has 4. It
   is the right answer for a deployment with real traffic, and
   `NOMINATIM_BASE_URL` is the setting that points at it.
4. **Give up on looking addresses up.** Rejected: it is a small part
   of the product and it works.
5. **An address typed by a customer is sent to a third party.** Not
   rejected, but noted: the address is a place, not a person, and the
   policy asks for personal data not to be sent. Nothing else about
   the customer is.

## Consequences

- A fresh checkout can look an address up with no account of any kind.
- A deployment that does not want a dependency on a donated service
  sets one value, and the product still works.
- The search can be slower than it was: a call waits for its turn, at
  most a second, and the answer for an address that has been asked
  before is instant.
- The rules are code, not a habit. A change that breaks one of them
  breaks a test: the throttle and the cache are looked at in the
  geocoder the application builds, and the calls are measured.
- The data is OpenStreetMap's and the attribution says so, on the
  pages where a person sees it. The data is under the ODbL, so a
  deployment that copied a great deal of it out would have to share
  alike; a point per shop is a small extraction, and the attribution
  is what the licence asks for.
- The limit is on the process, so it is the limit for the whole
  application as long as there is one API instance. The deployment is
  one instance (ADR 008), and a second one would need the limit to move
  somewhere shared, the same way the rate limiter would. A deployment
  that grows should point `NOMINATIM_BASE_URL` at its own instance,
  which is what the policy recommends anyway.
