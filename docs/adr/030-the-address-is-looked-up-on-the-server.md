# ADR 030: The address is looked up on the server, and the shop owner's own coordinates win

Date: 2026-10-22
Status: Accepted
Requirement: Phase 2, FR-22 and FR-23 (geo search and price comparison), sprint 7

## Context

A customer wants a print shop near them. Two things are missing from what
the platform has: a place to search *around* when the customer will not
share a location, and a way to put a new shop on the map without asking
its owner to type a pair of numbers.

The second one is the reason the owner asked for this sprint's first
task. A shop owner knows their own address. Asking them for a latitude
and a longitude is asking them to look something up, and about half of
them will get it wrong, or leave it out, and a shop with no point on the
map cannot be found by anybody.

The first one is the reason the sprint has a search at all. The
customer may share a location, or may refuse, and a customer who
refuses must still be able to look at the shops.

Both need somebody else's database of places. That is an external
service, it costs money, and it needs a key.

## Decision

**The server asks the map provider where an address is.** The customer
never holds the key and the browser never asks the provider. The
request goes to this application, the application asks the provider with
its own key, and the answer comes back as a point. A key in the
browser is a key that anybody can lift and use from their own machine;
this one stays on the server and is restricted by the address the
server calls from.

**The lookup is written with the standard library.** `urllib` and
`json` are enough for one request that returns JSON. No HTTP client is
added to the dependency list for it.

**There are two keys, not one.** `GOOGLE_MAPS_API_KEY` is for the
browser and is restricted by the websites that may use it.
`GOOGLE_GEOCODING_API_KEY` is for the server and is restricted by the
address the server calls from. A key that is given to a browser cannot
also be the server's secret.

**The shop owner's own coordinates win.** If the owner typed a latitude
and a longitude, they are used and the address is not looked up at all.
A shop owner knows where their own shop is better than a map does, and a
map will happily put a shop in the middle of a lake because the address
on the letter is short. The coordinates are the fallback, not the first
choice: when the owner gives only an address, the address is looked up.

**A deployment with no key still works.** There is no geocoder, and the
features that need one say so:

- a shop owner types the coordinates of their shop;
- a customer who cannot share a location sees the whole list;
- a customer who typed an address is told that this deployment cannot
  look one up, and is asked for the location instead.

Nothing is silently degraded. The refusal says which of the two
problems it is: an address nobody has heard of (`ADDRESS_NOT_FOUND`),
a provider that would not answer (`GEOCODING_UNAVAILABLE`), or a
deployment with no key and no way to place the shop
(`COORDINATES_REQUIRED`).

**The price on the search is the price of the order.** The search
computes the price with `domain.pricing.quote_paise`, the same function
the order flow uses, and a test creates a real order and compares the
two numbers. The search does not have its own arithmetic, because two
arithmetics drift apart.

**A shop that cannot do the job is not in the comparison.** When prices
are asked for, the rate for the chosen options is joined into the query,
so a shop without that rate is absent rather than present with a price
nobody can pay.

## Alternatives considered

1. **The browser asks the provider.** Rejected: the key would be in
   the page, and anybody reading the page could use it. It also cannot
   help the vendor, whose address is typed on a form that has to reach
   the server anyway.
2. **A geocoding library.** Rejected: one request, one JSON body and
   one query parameter. `httpx` is already a dependency for the tests
   and `urllib` is in the standard library, so a library would be added
   to say nothing the standard library does not.
3. **OpenStreetMap Nominatim instead of Google.** Rejected for now:
   its usage policy asks for a real identifying user agent and forbids
   heavy use, and the platform already names Google for the map in
   sprint 8. The gateway is an interface, so the provider is one file
   and one setting away from being changed.
4. **Ask the vendor for the coordinates always.** Rejected: it is the
   thing the owner asked to be fixed. It stays as the fallback for a
   deployment with no key.
5. **Store the address the provider read back.** Rejected for now: it
   would overwrite what the owner typed with the provider's guess. The
   address on the shop stays the owner's own words.

## Consequences

- A deployment that wants a typed address, or a shop that places
  itself, needs a key from the map provider and a little money on the
  account. Without one the platform is smaller, not broken.
- The geocoding request is the only request this application makes to
  a provider while a customer waits, so it has a timeout (five seconds)
  and the customer is told when it fails rather than left waiting.
- The key is a secret: it is in the environment, never in the
  repository, and never in the browser.
- The provider's answer is somebody else's opinion about where a place
  is. The tests use a geocoder that answers from a table, so the suite
  never depends on the provider being up.
