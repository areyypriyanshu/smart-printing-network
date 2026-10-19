import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import { server } from "../../test/msw/server";
import { renderWithProviders } from "../../test/render";
import { OrderPage } from "./order-page";

const order = {
  id: "22222222-2222-4222-8222-222222222222",
  order_no: 1042,
  status: "PAID",
  status_reason: null,
  shop_id: "shop-1",
  upload_id: "upload-1",
  page_count: 5,
  copies: 2,
  paper_size: "A4",
  color: false,
  duplex: false,
  rate_paise: 200,
  min_order_paise: 0,
  price_paise: 2000,
  pickup_code: "481902",
  paid_at: "2026-01-01T00:10:00Z",
  created_at: "2026-01-01T00:09:00Z",
};

function renderOrderPage() {
  return renderWithProviders(
    <Routes>
      <Route path="/orders/:orderId" element={<OrderPage />} />
    </Routes>,
    { route: `/orders/${order.id}` },
  );
}

describe("OrderPage", () => {
  it("shows the status, price, pickup code and history", async () => {
    server.use(
      http.get("/api/v1/orders/:id", () =>
        HttpResponse.json({
          order,
          events: [
            {
              from_status: null,
              to_status: "PENDING_PAYMENT",
              actor_type: "customer",
              reason: null,
              at: "2026-01-01T00:09:00Z",
            },
            {
              from_status: "PENDING_PAYMENT",
              to_status: "PAID",
              actor_type: "webhook",
              reason: null,
              at: "2026-01-01T00:10:00Z",
            },
          ],
        }),
      ),
    );

    renderOrderPage();

    expect(
      await screen.findByRole("heading", {
        name: "Paid, waiting for the shop",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("481902")).toBeInTheDocument();
    expect(screen.getByText(/₹\s?20\.00/)).toBeInTheDocument();
    const history = screen.getByRole("region", { name: "History" });
    expect(history).toHaveTextContent("Waiting for payment");
    expect(history).toHaveTextContent("Paid, waiting for the shop");
  });

  it("hides the pickup code before the order is paid", async () => {
    server.use(
      http.get("/api/v1/orders/:id", () =>
        HttpResponse.json({
          order: {
            ...order,
            status: "PENDING_PAYMENT",
            pickup_code: null,
            paid_at: null,
          },
          events: [],
        }),
      ),
    );

    renderOrderPage();

    expect(
      await screen.findByRole("heading", { name: "Waiting for payment" }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Pickup code")).not.toBeInTheDocument();
  });
});
