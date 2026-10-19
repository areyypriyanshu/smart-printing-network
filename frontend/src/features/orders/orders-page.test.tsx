import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { errorResponse } from "../../test/msw/handlers";
import { server } from "../../test/msw/server";
import { renderWithProviders } from "../../test/render";
import { OrdersPage } from "./orders-page";

const order = {
  id: "11111111-1111-4111-8111-111111111111",
  order_no: 7,
  status: "PAID",
  status_reason: null,
  shop_id: "22222222-2222-4222-8222-222222222222",
  upload_id: "33333333-3333-4333-8333-333333333333",
  page_count: 12,
  copies: 1,
  paper_size: "A4",
  color: false,
  duplex: true,
  rate_paise: 200,
  min_order_paise: 0,
  price_paise: 2400,
  pickup_code: "123456",
  paid_at: "2026-01-01T10:00:00Z",
  created_at: "2026-01-01T09:59:00Z",
};

describe("OrdersPage", () => {
  it("lists the customer's orders with their status and price", async () => {
    server.use(
      http.get("/api/v1/orders", () =>
        HttpResponse.json({ items: [order], next_cursor: null }),
      ),
    );
    renderWithProviders(<OrdersPage />, { route: "/orders" });

    expect(await screen.findByText("#7")).toBeInTheDocument();
    expect(screen.getByText("Paid, waiting for the shop")).toBeInTheDocument();
    expect(
      screen.getByText(/12 pages · 1 copy · A4 · Black and white/),
    ).toBeInTheDocument();
  });

  it("links each order to its detail page", async () => {
    server.use(
      http.get("/api/v1/orders", () =>
        HttpResponse.json({ items: [order], next_cursor: null }),
      ),
    );
    renderWithProviders(<OrdersPage />, { route: "/orders" });

    const link = await screen.findByRole("link", { name: /#7/ });
    expect(link).toHaveAttribute("href", `/orders/${order.id}`);
  });

  it("shows an empty state with a way to start an order", async () => {
    server.use(
      http.get("/api/v1/orders", () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
    );
    renderWithProviders(<OrdersPage />, { route: "/orders" });

    expect(
      await screen.findByText(/you have not placed an order yet/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /start a new order/i }),
    ).toBeInTheDocument();
  });

  it("shows an error state and a retry when the list cannot be loaded", async () => {
    server.use(
      http.get("/api/v1/orders", () =>
        errorResponse(500, "INTERNAL_ERROR", "Something went wrong"),
      ),
    );
    renderWithProviders(<OrdersPage />, { route: "/orders" });

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Try again" }),
    ).toBeInTheDocument();
  });
});
