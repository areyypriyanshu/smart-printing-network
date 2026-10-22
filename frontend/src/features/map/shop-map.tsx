import { useEffect, useRef, useState } from "react";

import type { ShopSearchItem } from "../../api/client";
import { sectionTitleClassName } from "../../components/ui";
import { formatPaise } from "../../lib/money";
import {
  loadGoogleMaps,
  mapsApiKey,
  type GoogleMaps,
  type LatLng,
  type MapsMap,
} from "./google-maps";

/**
 * The shops around the customer, on a map, with the price on each pin.
 *
 * The map is an addition to the list, never a replacement for it. The
 * list is what a customer reads, it works without a network and
 * without a key, and it is what a screen reader is given. So every
 * state of this component that is not a drawn map says so in words and
 * leaves the list alone.
 */

export type ShopMapProps = {
  shops: ShopSearchItem[];
  /** Where the customer is, when they said. The map is centred there. */
  center?: LatLng | null;
};

type Status = "waiting" | "loading" | "ready" | "failed";

const ZOOM = 13;

/** The middle of the pins, when the customer did not say where they are. */
function centreOf(shops: ShopSearchItem[]): LatLng | null {
  if (shops.length === 0) return null;
  const total = shops.reduce(
    (sum, shop) => ({
      lat: sum.lat + shop.latitude,
      lng: sum.lng + shop.longitude,
    }),
    { lat: 0, lng: 0 },
  );
  return { lat: total.lat / shops.length, lng: total.lng / shops.length };
}

/** What is written on the pin. The price, when there is one. */
function markerText(shop: ShopSearchItem): string {
  const price = shop.price_paise;
  if (price !== null && price !== undefined) return formatPaise(price);
  return shop.name;
}

export function ShopMap({ shops, center = null }: ShopMapProps) {
  const key = mapsApiKey();
  const [status, setStatus] = useState<Status>("waiting");
  const [maps, setMaps] = useState<GoogleMaps | null>(null);
  const [map, setMap] = useState<MapsMap | null>(null);
  const holder = useRef<HTMLDivElement | null>(null);
  const mapCenter = useRef<LatLng | null>(null);
  const centerLat = center?.lat;
  const centerLng = center?.lng;

  // The provider's script is fetched only when the map is nearly in
  // view. A customer who scrolls past the list never pays for it.
  useEffect(() => {
    if (key === "") return;
    let stopped = false;
    const start = () => {
      setStatus("loading");
      loadGoogleMaps(key)
        .then((arrived) => {
          if (stopped) return;
          setMaps(arrived);
          setStatus("ready");
        })
        .catch(() => {
          if (!stopped) setStatus("failed");
        });
    };
    const element = holder.current;
    if (element === null) return;
    let observer: IntersectionObserver | null = null;
    if (typeof IntersectionObserver === "undefined") {
      start();
    } else {
      observer = new IntersectionObserver(
        (entries) => {
          if (entries.some((entry) => entry.isIntersecting)) {
            observer?.disconnect();
            start();
          }
        },
        { rootMargin: "200px" },
      );
      observer.observe(element);
    }
    return () => {
      stopped = true;
      observer?.disconnect();
    };
  }, [key]);

  //: The centre the map should use on its first frame. It is kept in a
  //: ref so that the map is built once, when the provider's API arrives,
  //: rather than rebuilt every time the customer's position changes.
  useEffect(() => {
    mapCenter.current = center ?? centreOf(shops);
  }, [center, shops]);

  // The map itself is built once, when the provider's API has arrived.
  // It is not rebuilt when the shops or the customer's position change:
  // a second map on the same element would sit on top of the first one.
  useEffect(() => {
    if (maps === null) return;
    const element = holder.current;
    if (element === null) return;
    const instance = new maps.maps.Map(element, {
      center: mapCenter.current ?? { lat: 0, lng: 0 },
      zoom: ZOOM,
    });
    setMap(instance);
    return () => {
      element.replaceChildren();
    };
  }, [maps]);

  // The centre follows the customer, and falls back to the middle of the
  // shops when the customer clears their location.
  useEffect(() => {
    if (map === null) return;
    if (centerLat !== undefined && centerLng !== undefined) {
      map.setCenter({ lat: centerLat, lng: centerLng });
      return;
    }
    const middle = centreOf(shops);
    if (middle !== null) map.setCenter(middle);
  }, [map, centerLat, centerLng, shops]);

  // The pins are taken down again when the shops change or the component
  // goes away, so that a page that is left and come back to does not
  // draw two sets of pins on top of each other.
  useEffect(() => {
    if (maps === null || map === null) return;
    const markers = shops.map((shop) => {
      const price = shop.price_paise;
      return new maps.maps.Marker({
        position: { lat: shop.latitude, lng: shop.longitude },
        map,
        title:
          price === null || price === undefined
            ? shop.name
            : `${shop.name} — ${formatPaise(price)}`,
        label: {
          text: markerText(shop),
          color: "#1f2937",
          fontSize: "12px",
          fontWeight: "600",
        },
      });
    });
    return () => {
      for (const marker of markers) marker.setMap(null);
    };
  }, [maps, map, shops]);

  if (shops.length === 0) return null;

  if (key === "") {
    return (
      <section aria-label="The shops on a map" className="flex flex-col gap-2">
        <h3 className={sectionTitleClassName()}>On the map</h3>
        <p className="text-sm text-steel">
          The map is not switched on in this deployment. The list below has the
          same shops, with their prices.
        </p>
      </section>
    );
  }

  return (
    <section aria-label="The shops on a map" className="flex flex-col gap-3">
      <h3 className={sectionTitleClassName()}>On the map</h3>
      <div
        ref={holder}
        role="region"
        aria-label="A map of the shops around you, with the price on each pin"
        className="h-72 w-full overflow-hidden rounded-lg border border-hairline-soft"
      />
      {(status === "waiting" || status === "loading") && (
        <p role="status" className="text-sm text-steel">
          Loading the map…
        </p>
      )}
      {status === "failed" && (
        <p role="status" className="text-sm text-steel">
          The map could not be loaded. The list below has the same shops, with
          their prices.
        </p>
      )}
      <p className="text-xs text-steel">
        The map is drawn by Google. The list below is the same shops, with their
        prices, and it works without the map.
      </p>
    </section>
  );
}
