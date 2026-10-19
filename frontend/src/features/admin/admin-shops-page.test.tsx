import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { errorResponse } from "../../test/msw/handlers";
import { server } from "../../test/msw/server";
import { renderWithProviders } from "../../test/render";
import { AdminShopsPage } from "./admin-shops-page";

type AdminShop = {
  id: string;
  name: string;
  address: string;
  owner_email: string;
  owner_full_name: string;
  latitude: number;
  longitude: number;
  is_verified: boolean;
  accepting_orders: boolean;
  rate_count: number;
  created_at: string;
  updated_at: string;
};

function shop(overrides: Partial<AdminShop> = {}): AdminShop {
  return {
    id: "33333333-3333-4333-8333-333333333333",
    name: "Kharghar Print Hub",
    address: "Sector 12, Kharghar",
    owner_email: "owner@example.com",
    owner_full_name: "Owner One",
    latitude: 19.0473,
    longitude: 73.0699,
    is_verified: false,
    accepting_orders: true,
    rate_count: 8,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}

function useShopHandlers(
  items: AdminShop[],
  options: { approveStatus?: number } = {},
) {
  server.use(
    http.get("/api/v1/admin/shops", () =>
      HttpResponse.json({ items, next_cursor: null }),
    ),
    http.get("/api/v1/admin/actions", () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.post("/api/v1/admin/shops/:shopId/approve", () =>
      options.approveStatus === undefined
        ? HttpResponse.json(shop({ is_verified: true }))
        : errorResponse(
            options.approveStatus,
            "SHOP_ALREADY_VERIFIED",
            "This shop is already approved and taking orders.",
          ),
    ),
  );
}

describe("AdminShopsPage", () => {
  it("lists the shops that are waiting for a decision", async () => {
    useShopHandlers([shop()]);
    renderWithProviders(<AdminShopsPage />, { route: "/admin/shops" });

    expect(
      await screen.findByRole("heading", { name: "Kharghar Print Hub" }),
    ).toBeInTheDocument();
    expect(screen.getByText("owner@example.com")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Approve" })).toBeInTheDocument();
  });

  it("says so when nothing is waiting", async () => {
    useShopHandlers([]);
    renderWithProviders(<AdminShopsPage />, { route: "/admin/shops" });

    expect(
      await screen.findByText("No shops are waiting for a decision."),
    ).toBeInTheDocument();
  });

  it("shows the loading state before the shops arrive", () => {
    server.use(
      http.get("/api/v1/admin/shops", () => new Promise(() => {})),
      http.get("/api/v1/admin/actions", () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    );
    renderWithProviders(<AdminShopsPage />, { route: "/admin/shops" });

    expect(screen.getByText("Loading shops…")).toBeInTheDocument();
  });

  it("approves a shop when the approve button is pressed", async () => {
    let approved = false;
    server.use(
      http.get("/api/v1/admin/shops", () =>
        HttpResponse.json({ items: [shop()], next_cursor: null }),
      ),
      http.get("/api/v1/admin/actions", () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.post("/api/v1/admin/shops/:shopId/approve", () => {
        approved = true;
        return HttpResponse.json(shop({ is_verified: true }));
      }),
    );
    renderWithProviders(<AdminShopsPage />, { route: "/admin/shops" });

    await userEvent.click(
      await screen.findByRole("button", { name: "Approve" }),
    );

    await waitFor(() => expect(approved).toBe(true));
  });

  it("asks for a reason before suspending a shop", async () => {
    useShopHandlers([shop({ is_verified: true })]);
    renderWithProviders(<AdminShopsPage />, { route: "/admin/shops" });

    await userEvent.click(
      await screen.findByRole("button", { name: "Suspend" }),
    );

    expect(
      await screen.findByRole("heading", {
        name: "Suspend Kharghar Print Hub",
      }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Reason")).toBeInTheDocument();
  });

  it("will not suspend a shop without a reason", async () => {
    useShopHandlers([shop({ is_verified: true })]);
    renderWithProviders(<AdminShopsPage />, { route: "/admin/shops" });

    await userEvent.click(
      await screen.findByRole("button", { name: "Suspend" }),
    );
    await userEvent.click(
      await screen.findByRole("button", { name: "Suspend shop" }),
    );

    expect(
      await screen.findByText(
        "Give a reason. It goes into the moderation log.",
      ),
    ).toBeInTheDocument();
  });

  it("shows the error when the server refuses the approval", async () => {
    useShopHandlers([shop()], { approveStatus: 409 });
    renderWithProviders(<AdminShopsPage />, { route: "/admin/shops" });

    await userEvent.click(
      await screen.findByRole("button", { name: "Approve" }),
    );

    expect(
      await screen.findByText(
        "This shop is already approved and taking orders.",
      ),
    ).toBeInTheDocument();
  });
});
