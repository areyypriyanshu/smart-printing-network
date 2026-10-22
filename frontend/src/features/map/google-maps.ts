/**
 * The map, loaded when it is wanted.
 *
 * The map is the only part of this application that needs somebody
 * else's code in the page. It is not bundled: the provider's script is
 * fetched from the provider, and it is fetched when the customer
 * scrolls the map into view rather than when the page opens. A customer
 * who never looks at the map never waits for it, and a deployment with
 * no key for the map never asks for it at all.
 *
 * The key is not a secret. It is in the page, and anybody can read it
 * out of the page. What makes it safe is the restriction in the
 * provider's own console: the key is allowed to be used only by the
 * websites that may use it, and only by the one API that is allowed to
 * answer it. A stolen key that is restricted this way is worth nothing
 * to the person who stole it, because the request it makes does not
 * come from a website on the list.
 *
 * The types here are the small part of the provider's API that this
 * application uses. The full API is much larger, and typing all of it
 * would be a lot of code that says nothing about what the application
 * does.
 */

export const MAPS_SCRIPT_ID = "spn-google-maps";

export const MAPS_SCRIPT_ORIGIN = "https://maps.googleapis.com";

export type LatLng = { lat: number; lng: number };

export type MapsLabel = {
  text: string;
  color?: string;
  fontSize?: string;
  fontWeight?: string;
};

export type MapsMarkerOptions = {
  position: LatLng;
  map: MapsMap;
  title: string;
  label?: MapsLabel;
};

export type MapsMap = {
  setCenter(position: LatLng): void;
  setZoom(zoom: number): void;
};

export type MapsMarker = {
  setMap(map: MapsMap | null): void;
};

export type GoogleMaps = {
  maps: {
    Map: new (
      element: HTMLElement,
      options: { center: LatLng; zoom: number },
    ) => MapsMap;
    Marker: new (options: MapsMarkerOptions) => MapsMarker;
  };
};

declare global {
  interface Window {
    google?: GoogleMaps;
  }

  interface ImportMetaEnv {
    readonly VITE_GOOGLE_MAPS_API_KEY?: string;
  }
}

/** The key this deployment was built with, or an empty string. */
export function mapsApiKey(): string {
  const key = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
  return typeof key === "string" ? key.trim() : "";
}

/** The address the provider's script is fetched from. */
export function mapsScriptUrl(apiKey: string): string {
  const params = new URLSearchParams({ key: apiKey });
  return `${MAPS_SCRIPT_ORIGIN}/maps/api/js?${params.toString()}`;
}

//: The load that is in flight, or the one that has already happened.
//: The provider's script is fetched once for the whole page, and every
//: part of the page that wants a map waits for the same promise.
let pending: Promise<GoogleMaps> | null = null;

/**
 * The provider's API, once it has arrived.
 *
 * A failed attempt is forgotten, so that a customer whose network was
 * down for a moment can try again and the map can still appear.
 */
export function loadGoogleMaps(apiKey: string): Promise<GoogleMaps> {
  if (pending !== null) return pending;
  pending = new Promise<GoogleMaps>((resolve, reject) => {
    if (typeof document === "undefined") {
      reject(new Error("The map needs a browser."));
      return;
    }
    const already = window.google;
    if (already !== undefined) {
      resolve(already);
      return;
    }
    const script = document.createElement("script");
    script.id = MAPS_SCRIPT_ID;
    script.async = true;
    script.defer = true;
    script.src = mapsScriptUrl(apiKey);
    //: The script is taken out of the page when it failed, so that a
    //: later attempt adds one script rather than a second one beside a
    //: dead one. The identifier would otherwise belong to the dead
    //: script, and the page would carry two loads of the same API.
    const forget = () => {
      script.remove();
    };
    script.addEventListener("load", () => {
      const maps = window.google;
      if (maps === undefined) {
        forget();
        reject(new Error("The map did not arrive."));
        return;
      }
      resolve(maps);
    });
    script.addEventListener("error", () => {
      forget();
      reject(new Error("The map could not be fetched."));
    });
    document.head.appendChild(script);
  });
  pending.catch(() => {
    pending = null;
  });
  return pending;
}
