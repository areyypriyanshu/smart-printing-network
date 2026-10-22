import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The loader, on its own.
 *
 * The module keeps the load that is in flight, so every test starts
 * with a fresh copy of it. Otherwise the first test's promise would be
 * the answer to every later question.
 */

type MapsModule = typeof import("./google-maps");

async function freshModule(): Promise<MapsModule> {
  const module = await import("./google-maps");
  return module;
}

function scriptInHead(): HTMLScriptElement | null {
  return document.querySelector<HTMLScriptElement>("script#spn-google-maps");
}

describe("loading the map", () => {
  beforeEach(() => {
    vi.resetModules();
    document.head.innerHTML = "";
    delete window.google;
  });

  afterEach(() => {
    document.head.innerHTML = "";
    delete window.google;
  });

  it("asks the provider for the script with the key in the address", async () => {
    const { loadGoogleMaps } = await freshModule();
    const loading = loadGoogleMaps("key-123");

    const script = scriptInHead();
    expect(script).not.toBeNull();
    expect(script?.src).toContain("https://maps.googleapis.com/maps/api/js");
    expect(script?.src).toContain("key=key-123");

    window.google = { maps: { Map: class {}, Marker: class {} } } as never;
    script?.dispatchEvent(new Event("load"));
    await expect(loading).resolves.toBe(window.google);
  });

  it("fetches the script once for the whole page", async () => {
    const { loadGoogleMaps } = await freshModule();
    const first = loadGoogleMaps("key-123");
    const second = loadGoogleMaps("key-123");

    expect(document.querySelectorAll("script#spn-google-maps")).toHaveLength(1);
    expect(second).toBe(first);

    window.google = { maps: { Map: class {}, Marker: class {} } } as never;
    scriptInHead()?.dispatchEvent(new Event("load"));
    await expect(first).resolves.toBe(window.google);
  });

  it("forgets an attempt that failed, so the map can be tried again", async () => {
    const { loadGoogleMaps } = await freshModule();
    const failed = loadGoogleMaps("key-123");
    scriptInHead()?.dispatchEvent(new Event("error"));
    await expect(failed).rejects.toThrow();

    const retried = loadGoogleMaps("key-123");
    expect(document.querySelectorAll("script#spn-google-maps")).toHaveLength(1);
    window.google = { maps: { Map: class {}, Marker: class {} } } as never;
    scriptInHead()?.dispatchEvent(new Event("load"));
    await expect(retried).resolves.toBe(window.google);
  });

  it("says so when the key is not set", async () => {
    const { mapsApiKey } = await freshModule();
    vi.stubEnv("VITE_GOOGLE_MAPS_API_KEY", "");
    expect(mapsApiKey()).toBe("");
    vi.unstubAllEnvs();
  });
});
