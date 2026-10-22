import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import type { ShopSearchItem, UploadResponse } from "../../api/client";
import { errorResponse } from "../../test/msw/handlers";
import { server } from "../../test/msw/server";
import { renderWithProviders } from "../../test/render";
import { SearchPage } from "./search-page";

type PositionCallback = (position: GeolocationPosition) => void;
type PositionErrorCallback = (error: GeolocationPositionError) => void;

const uploadFixture: UploadResponse = {
  id: "11111111-1111-4111-8111-111111111111",
  original_filename: "notes.pdf",
  page_count: 5,
  size_bytes: 2048,
  created_at: "2026-01-01T00:00:00Z",
};

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
  price_paise: 2500,
  rate_paise: 500,
};

function useSearchHandlers(items: ShopSearchItem[] = [alpha, beta]) {
  server.use(
    http.get("/api/v1/shops/search", () => HttpResponse.json({ items })),
    http.post("/api/v1/uploads", () =>
      HttpResponse.json(uploadFixture, { status: 201 }),
    ),
  );
}

describe("the shop search", () => {
  it("shows the shops and how far away they are", async () => {
    useSearchHandlers();
    renderWithProviders(<SearchPage />, { route: "/shops" });

    const list = await screen.findByRole("list");
    const names = within(list)
      .getAllByRole("heading", { level: 3 })
      .map((heading) => heading.textContent);
    expect(names).toEqual(["Alpha Prints", "Beta Print Hub"]);
    expect(screen.getByText(/120 m away/)).toBeInTheDocument();
    expect(screen.getByText(/2\.4 km away/)).toBeInTheDocument();
  });

  it("says so when there are no shops", async () => {
    useSearchHandlers([]);
    renderWithProviders(<SearchPage />, { route: "/shops" });

    expect(
      await screen.findByText(/no shops within 5 km/i),
    ).toBeInTheDocument();
  });

  it("asks the browser for a location and searches around it", async () => {
    const asked: string[] = [];
    server.use(
      http.get("/api/v1/shops/search", ({ request }) => {
        asked.push(request.url);
        return HttpResponse.json({ items: [alpha] });
      }),
    );
    const getCurrentPosition = vi.fn((success: PositionCallback) => {
      success({
        coords: { latitude: 19.07, longitude: 72.87 },
      } as GeolocationPosition);
    });
    vi.stubGlobal("navigator", {
      ...navigator,
      geolocation: { getCurrentPosition },
    });
    const user = userEvent.setup();
    renderWithProviders(<SearchPage />, { route: "/shops" });

    await user.click(
      await screen.findByRole("button", { name: /find shops near me/i }),
    );

    expect(getCurrentPosition).toHaveBeenCalled();
    await screen.findByRole("button", { name: /showing shops near me/i });
    const last = asked[asked.length - 1];
    expect(last).toContain("latitude=19.07");
    expect(last).toContain("longitude=72.87");
    vi.unstubAllGlobals();
  });

  it("carries on with every shop when the browser refuses the location", async () => {
    useSearchHandlers();
    vi.stubGlobal("navigator", {
      ...navigator,
      geolocation: {
        getCurrentPosition: (
          _success: PositionCallback,
          failure?: PositionErrorCallback | null,
        ) =>
          failure?.({ code: 1, message: "denied" } as GeolocationPositionError),
      },
    });
    const user = userEvent.setup();
    renderWithProviders(<SearchPage />, { route: "/shops" });

    await user.click(
      await screen.findByRole("button", { name: /find shops near me/i }),
    );

    expect(
      await screen.findByText(/could not find your location/i),
    ).toBeInTheDocument();
    // The list is still there: the customer can still pick a shop.
    expect(screen.getByText("Alpha Prints")).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("searches around a typed address", async () => {
    const asked: string[] = [];
    server.use(
      http.get("/api/v1/shops/search", ({ request }) => {
        asked.push(request.url);
        return HttpResponse.json({ items: [alpha] });
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<SearchPage />, { route: "/shops" });

    await user.type(
      await screen.findByLabelText(/type an area or address/i),
      "Salt Lake",
    );
    await user.click(screen.getByRole("button", { name: /search this area/i }));

    await screen.findByText("Alpha Prints");
    expect(asked[asked.length - 1]).toContain("address=Salt+Lake");
  });

  it("asks for a typed address once, and not once per letter", async () => {
    // The map provider's policy forbids an autocomplete built on its
    // API, and it is right to forbid it: one lookup per keystroke spends
    // the whole application's budget of one call a second, and the
    // answer to "S" is of no use to anybody.
    const asked: string[] = [];
    server.use(
      http.get("/api/v1/shops/search", ({ request }) => {
        asked.push(request.url);
        return HttpResponse.json({ items: [alpha] });
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<SearchPage />, { route: "/shops" });

    await user.type(
      await screen.findByLabelText(/type an area or address/i),
      "Salt Lake",
    );

    // Nothing was asked for the address yet: the person has not said
    // so. (The page asks for the whole list when it opens, which is a
    // different thing.)
    expect(asked.filter((url) => url.includes("address="))).toEqual([]);

    await user.click(screen.getByRole("button", { name: /search this area/i }));

    await screen.findByText("Alpha Prints");
    const withAddress = asked.filter((url) => url.includes("address="));
    expect(withAddress).toHaveLength(1);
    expect(withAddress[0]).toContain("address=Salt+Lake");
  });

  it("shows what each shop would charge for the file", async () => {
    useSearchHandlers();
    const user = userEvent.setup({ applyAccept: false });
    renderWithProviders(<SearchPage />, { route: "/shops" });

    await user.upload(
      await screen.findByLabelText(/choose a file to compare prices/i),
      new File(["hello"], "notes.pdf", { type: "application/pdf" }),
    );

    expect(await screen.findByText(/notes\.pdf/)).toBeInTheDocument();
    // The price is the server's. It is never worked out in the browser.
    expect(await screen.findByText("₹10.00")).toBeInTheDocument();
  });

  it("cannot sort by price until there is a file to price", async () => {
    useSearchHandlers();
    renderWithProviders(<SearchPage />, { route: "/shops" });

    const sort = await screen.findByLabelText(/order by/i);
    const cheapest = within(sort).getByRole("option", {
      name: /cheapest first/i,
    }) as HTMLOptionElement;
    expect(cheapest.disabled).toBe(true);
  });

  it("says how far the closest shop is when the radius is empty", async () => {
    // A customer who is told "there is nothing near you" and nothing
    // else is left guessing.
    server.use(
      http.get("/api/v1/shops/search", () =>
        HttpResponse.json({
          items: [],
          nearest: {
            name: "Central Prints",
            address: "12 Esplanade Row, Kolkata",
            distance_m: 12600,
          },
        }),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<SearchPage />, { route: "/shops" });

    await screen.findByText(/no shops within 5 km/i);
    const line = screen.getByText(/closest one is Central Prints/i);
    expect(line).toHaveTextContent(/at 12 Esplanade Row/i);
    expect(line).toHaveTextContent(/12.6 km away/i);

    // And there is a way out of it.
    // The button widens the search to the next radius that reaches the
    // closest shop.
    await user.click(
      screen.getByRole("button", { name: /show shops up to 25 km/i }),
    );
    await waitFor(() =>
      expect(screen.getByLabelText(/how far/i)).toHaveValue("25000"),
    );
  });

  it("says who the map data came from", async () => {
    // The free provider asks for its attribution to be shown wherever
    // its data is shown, and it is not optional.
    server.use(
      http.get("/api/v1/shops/search", () =>
        HttpResponse.json({
          items: [alpha],
          attribution: "© OpenStreetMap contributors",
        }),
      ),
    );
    renderWithProviders(<SearchPage />, { route: "/shops" });

    expect(
      await screen.findByText(/OpenStreetMap contributors/),
    ).toBeInTheDocument();
  });

  it("says what the failure was when the search fails", async () => {
    server.use(
      http.get("/api/v1/shops/search", () =>
        errorResponse(503, "GEOCODING_UNAVAILABLE", "No key"),
      ),
    );
    renderWithProviders(<SearchPage />, { route: "/shops" });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /cannot look up an address/i,
    );
  });
});
