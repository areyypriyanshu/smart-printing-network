# ADR 032: The map is drawn last, and the list is the map that always works

Date: 2026-10-22
Status: Accepted
Requirement: Phase 2, FR-24 (map view), sprint 8

## Context

The customer can already find the shops around them and compare their
prices (FR-22 and FR-23). FR-24 adds the map: the same shops on a map,
with the price on each pin.

A map is different from every other screen in this application. It needs
somebody else's JavaScript in the page, it talks to somebody else's
servers from the browser, and it needs a key that is visible to anybody
who opens the page. It is the only third-party script besides the
identity provider and the payment checkout, and it is the only one that
is not on the critical path of an order.

The map must not become the only way to see the shops. A customer with a
slow connection, a blocked script, a content blocker, a deployment with
no key, or a screen reader still has to be able to compare prices and
order.

## Decision

**The map is an addition to the list, and the list is the product.** The
list shows the same shops, the same distances and the same prices, and
it is what the page shows while the map is loading, after the map
failed, and when the deployment has no key. The map is never the only
way to reach a shop.

**The provider's script is fetched when the map is wanted.** An
`IntersectionObserver` waits until the map is nearly in view, then adds
the script to the page. A customer who never scrolls to the map never
downloads it, and the first paint of the search page does not wait for
it. The script is fetched once for the whole page, and a later attempt
reuses the same promise. A failed attempt is forgotten and its script
element is removed, so a second attempt adds one script rather than a
second one beside a dead one.

**The key is public, and the restriction is the security boundary.** A
key in a page can be read by anybody who opens the page; that is how a
browser key works. What makes it safe is the restriction in the
provider's console: it is allowed only by the websites on the list and
only for the Maps JavaScript API. A key that is not restricted is a key
that somebody else will spend. The key is `VITE_GOOGLE_MAPS_API_KEY`,
baked into the bundle at build time, because the bundle is built once
and served as static files. The server's geocoding key is a different
key and never reaches the browser (ADR 030).

**No key is a state, not a bug.** A deployment without a key still runs
the search; the map section says that the map is not switched on and
that the list has the same shops and prices. A key that is set but whose
script fails says that too. Neither state is silent.

**The price on the pin is the price from the server.** The label is
`format_paise(shop.price_paise)`, the same number the list shows, which
comes from the same pricing function the order uses (ADR 010). The map
does no arithmetic.

**The content security policy allows the provider by name.** The script,
the tiles and the requests the map makes from the page are named in
`script-src`, `img-src` and `connect-src`. The policy is not widened to
`https:` or to a wildcard that would allow everything.

## Alternatives considered

1. **A static map image from the provider.** Rejected: the requirement
   is a map with a marker and a price for each shop, and a static image
   cannot show which pin belongs to which price without drawing the
   labels into the image on the server. It would also put the geocoding
   key or a second server-side key on the image URL.
2. **An embedded iframe from the provider.** Rejected: the page cannot
   put a price on each pin inside an iframe it does not control, and the
   iframe has its own loading and consent behaviour that the application
   cannot describe to the customer.
3. **Leaflet and OpenStreetMap tiles.** Reasonable, and the geocoder is
   already OpenStreetMap's (ADR 031). Rejected for this sprint because
   the requirement names Google Maps, and the provider is behind one
   module: changing it is one file and one key, not a redesign.
4. **Loading the map on page open.** Rejected: every customer would pay
   for a script many of them never look at, including the ones who only
   want the price list.
5. **Making the map the primary view, with a toggle to the list.**
   Rejected: the list works without JavaScript from a third party, is
   keyboard operable and is what a screen reader reads. The map can be
   missing; the list cannot.

## Consequences

- A deployment that wants the map needs a Google Cloud project, the Maps
  JavaScript API enabled, a billing account, and a key restricted by
  HTTP referrers. Without one the platform is smaller, not broken.
- The page now depends on a third party for one optional feature. The
  CSP names the hosts, the loading is lazy, and a failure is a sentence.
- The map is not covered by a browser test that draws real tiles,
  because that would need a real key in CI. The component tests cover
  the loader, the lazy start, the pins, the failure state and the
  no-key state; the list is covered by the search tests and Playwright.
- The provider's terms, the marker API and the price of the API can
  change. The map is one module (`frontend/src/features/map/`), so the
  provider can be replaced without touching the search screen.

## Revisit when

- The provider's terms no longer allow this use, or the key restriction
  cannot be enforced in the console.
- A second map provider is wanted, or the map has to work offline.
- The map becomes the only way to reach a shop in a design change. It
  must not.
