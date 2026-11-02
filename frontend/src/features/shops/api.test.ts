import { afterEach, describe, expect, it, vi } from "vitest";

import { listNearbyShops, listShops } from "./api";

function page(name: string, next_cursor: string | null) {
  return {
    items: [{ id: name, name }],
    next_cursor,
    attribution: null,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("shop list pagination", () => {
  it("loads every page for the regular shop list", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(page("first", "next"))),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(page("second", null))),
      );
    vi.stubGlobal("fetch", fetchMock);

    const result = await listShops();

    expect(result.items.map((shop) => shop.name)).toEqual(["first", "second"]);
    expect(result.next_cursor).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain("cursor=next");
  });

  it("loads every page for nearby shops while retaining the location", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(JSON.stringify(page("first", "next"))),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify(page("second", null))),
      );
    vi.stubGlobal("fetch", fetchMock);

    const result = await listNearbyShops({ latitude: 22.5, longitude: 88.3 });

    expect(result.items.map((shop) => shop.name)).toEqual(["first", "second"]);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain("latitude=22.5");
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain("longitude=88.3");
    expect(String(fetchMock.mock.calls[1]?.[0])).toContain("cursor=next");
  });

  it("stops if the server repeats a cursor", async () => {
    const repeated = JSON.stringify(page("first", "same"));
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockImplementation(async () => new Response(repeated));
    vi.stubGlobal("fetch", fetchMock);

    await expect(listShops()).rejects.toThrow("repeated page cursor");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
