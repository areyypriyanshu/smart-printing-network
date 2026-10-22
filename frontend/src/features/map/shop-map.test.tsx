import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ShopSearchItem } from "../../api/client";
import { TestProviders, renderWithProviders } from "../../test/render";

/**
 * The map, as the page uses it.
 *
 * The map is never the only way to see the shops. A customer with no
 * key, a blocked script or a browser that refused the location still
 * has the list, so every failure here is a sentence rather than an
 * empty box.
 */

const alpha: ShopSearchItem = {
  id: "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa",
  name: "Alpha Prints",
  address: "1 Main Street",
  latitude: 19.07,
  longitude: 72.87,
  min_order_paise: 0,
  distance_m: 120,
  price_paise: 1000,
  rate_paise: 200,
};

const beta: ShopSearchItem = {
  id: "bbbbbbbb-1111-4111-8111-bbbbbbbbbbbb",
  name: "Beta Print Hub",
  address: "2 Market Road",
  latitude: 19.08,
  longitude: 72.88,
  min_order_paise: 0,
  distance_m: 2400,
  price_paise: null,
  rate_paise: null,
};

type MarkerOptions = {
  position: { lat: number; lng: number };
  title: string;
  label?: { text: string };
};

type FakeMarker = {
  options: MarkerOptions;
  setMap: ReturnType<typeof vi.fn>;
};

let markers: FakeMarker[] = [];

class FakeMap {
  static instances: FakeMap[] = [];

  setCenter = vi.fn();
  setZoom = vi.fn();

  constructor() {
    FakeMap.instances.push(this);
  }
}

class FakeMarkerClass {
  options: MarkerOptions;
  setMap = vi.fn();

  constructor(options: MarkerOptions) {
    this.options = options;
    markers.push(this);
  }
}

function installMaps(): void {
  window.google = {
    maps: {
      Map: FakeMap,
      Marker: FakeMarkerClass,
    },
  } as never;
}

async function renderMap({
  apiKey = "",
  center = null,
}: {
  apiKey?: string;
  center?: { lat: number; lng: number } | null;
} = {}) {
  vi.resetModules();
  vi.stubEnv("VITE_GOOGLE_MAPS_API_KEY", apiKey);
  const { ShopMap } = await import("./shop-map");
  const result = renderWithProviders(
    <ShopMap shops={[alpha, beta]} center={center} />,
  );
  return { ...result, ShopMap };
}

describe("the shop map", () => {
  beforeEach(() => {
    vi.resetModules();
    markers = [];
    FakeMap.instances = [];
    document.head.innerHTML = "";
    delete window.google;
    vi.stubGlobal("IntersectionObserver", undefined);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.resetModules();
    document.head.innerHTML = "";
    delete window.google;
  });

  it("says so when the deployment has no map key", async () => {
    await renderMap();

    expect(
      screen.getByText(/the map is not switched on in this deployment/i),
    ).toBeInTheDocument();
    expect(
      document.querySelector("script#spn-google-maps"),
    ).not.toBeInTheDocument();
  });

  it("waits until the map is nearly in view before asking for it", async () => {
    const notifier: { fire?: () => void } = {};
    class FakeIntersectionObserver {
      constructor(callback: IntersectionObserverCallback) {
        notifier.fire = () =>
          callback(
            [{ isIntersecting: true } as IntersectionObserverEntry] as never,
            this as never,
          );
      }
      observe() {}
      disconnect() {}
    }
    vi.stubGlobal("IntersectionObserver", FakeIntersectionObserver);

    await renderMap({ apiKey: "key-123" });

    expect(
      document.querySelector("script#spn-google-maps"),
    ).not.toBeInTheDocument();
    expect(screen.getByText(/loading the map/i)).toBeInTheDocument();

    notifier.fire?.();

    await waitFor(() => {
      const script = document.querySelector<HTMLScriptElement>(
        "script#spn-google-maps",
      );
      expect(script?.src).toContain("key=key-123");
    });
  });

  it("draws a pin for each shop, with its price when it has one", async () => {
    installMaps();

    await renderMap({ apiKey: "key-123", center: { lat: 19.07, lng: 72.87 } });

    await waitFor(() => expect(markers).toHaveLength(2));

    expect(markers[0].options.position).toEqual({ lat: 19.07, lng: 72.87 });
    expect(markers[0].options.title).toContain("Alpha Prints");
    expect(markers[0].options.title).toContain("₹10.00");
    expect(markers[0].options.label?.text).toBe("₹10.00");

    // A shop with no price is still a pin, and its label is its name.
    expect(markers[1].options.label?.text).toBe("Beta Print Hub");
  });

  it("keeps one map when the centre moves, and moves its centre", async () => {
    installMaps();
    vi.stubEnv("VITE_GOOGLE_MAPS_API_KEY", "key-123");
    const { ShopMap } = await import("./shop-map");

    // The wrapper is given to the testing library rather than rendered
    // by hand, so a re-render keeps the component and its map instead
    // of replacing both.
    const { rerender } = render(
      <ShopMap shops={[alpha, beta]} center={{ lat: 19.07, lng: 72.87 }} />,
      { wrapper: TestProviders },
    );
    await waitFor(() => expect(markers).toHaveLength(2));

    rerender(
      <ShopMap shops={[alpha, beta]} center={{ lat: 19.1, lng: 72.91 }} />,
    );

    expect(FakeMap.instances).toHaveLength(1);
    await waitFor(() =>
      expect(FakeMap.instances[0].setCenter).toHaveBeenLastCalledWith({
        lat: 19.1,
        lng: 72.91,
      }),
    );
  });

  it("takes the pins down when the page moves on", async () => {
    installMaps();

    const { unmount } = await renderMap({ apiKey: "key-123" });
    await waitFor(() => expect(markers).toHaveLength(2));

    unmount();

    for (const marker of markers) {
      expect(marker.setMap).toHaveBeenCalledWith(null);
    }
  });

  it("says the map failed, and leaves the list to the rest of the page", async () => {
    await renderMap({ apiKey: "key-123" });

    const script = document.querySelector<HTMLScriptElement>(
      "script#spn-google-maps",
    );
    expect(script).not.toBeNull();
    script?.dispatchEvent(new Event("error"));

    expect(
      await screen.findByText(/the map could not be loaded/i),
    ).toBeInTheDocument();
  });
});
