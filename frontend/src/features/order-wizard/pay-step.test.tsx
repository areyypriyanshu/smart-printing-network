import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "../../test/msw/server";
import { renderWithProviders } from "../../test/render";
import { PayStep } from "./pay-step";

const upload = {
  id: "11111111-1111-4111-8111-111111111111",
  original_filename: "notes.pdf",
  page_count: 5,
  size_bytes: 2048,
  created_at: "2026-01-01T00:00:00Z",
};

const shop = { id: "shop-1", name: "Alpha Prints", address: "1 Main Street" };

const quote = {
  price_paise: 2000,
  rate_paise: 200,
  min_order_paise: 0,
};

const options = {
  paper_size: "A4" as const,
  color: false,
  duplex: false,
  copies: 2,
};

const order = {
  id: "22222222-2222-4222-8222-222222222222",
  order_no: 1042,
  status: "PAID",
  status_reason: null,
  shop_id: shop.id,
  upload_id: upload.id,
  page_count: 5,
  copies: 2,
  paper_size: "A4",
  color: false,
  duplex: false,
  rate_paise: 200,
  min_order_paise: 0,
  price_paise: 2000,
  pickup_code: "481902",
  payment_method: "online",
  paid_at: "2026-01-01T00:10:00Z",
  created_at: "2026-01-01T00:09:00Z",
};

const cashOrder = {
  ...order,
  status: "RESERVED",
  payment_method: "at_store",
  paid_at: null,
};

function renderPayStep(
  props: {
    paymentMethod?: "online" | "at_store";
    cashAtStoreEnabled?: boolean;
    onPaymentMethodChange?: (method: "online" | "at_store") => void;
  } = {},
) {
  return renderWithProviders(
    <PayStep
      upload={upload}
      options={options}
      shop={shop}
      quote={quote}
      paymentMethod={props.paymentMethod ?? "online"}
      cashAtStoreEnabled={props.cashAtStoreEnabled ?? false}
      onPaymentMethodChange={props.onPaymentMethodChange ?? (() => undefined)}
      onBack={() => undefined}
      deadlineMs={100}
    />,
    { route: "/new" },
  );
}

function useHappyPathHandlers() {
  server.use(
    http.post("/api/v1/orders", () =>
      HttpResponse.json(
        {
          order: { ...order, status: "PENDING_PAYMENT", pickup_code: null },
          payment: {
            provider: "fake",
            provider_order_id: "fake_order_1",
            amount_paise: 2000,
            currency: "INR",
            key_id: null,
          },
        },
        { status: 201 },
      ),
    ),
    http.post("/api/v1/testing/simulate-payment", () =>
      HttpResponse.json({ status: "paid" }),
    ),
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
}

describe("PayStep", () => {
  it("creates the order and shows the pickup code once payment lands", async () => {
    useHappyPathHandlers();
    const user = userEvent.setup();
    renderPayStep();

    await user.click(screen.getByRole("button", { name: /pay/i }));

    expect(await screen.findByText("Payment received")).toBeInTheDocument();
    expect(screen.getByText("481902")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View order" })).toHaveAttribute(
      "href",
      `/orders/${order.id}`,
    );
  });

  it("shows the server message when the order cannot be created", async () => {
    server.use(
      http.post("/api/v1/orders", () =>
        HttpResponse.json(
          {
            error: {
              code: "UPLOAD_ALREADY_USED",
              message: "This file is already attached to an order",
              details: {},
              request_id: "req-1",
            },
          },
          { status: 409 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderPayStep();

    await user.click(screen.getByRole("button", { name: /pay/i }));

    expect(
      await screen.findByText("This file is already attached to an order."),
    ).toBeInTheDocument();
  });

  it("does not offer paying at the shop when the platform has it off", () => {
    useHappyPathHandlers();
    renderPayStep({ cashAtStoreEnabled: false });

    expect(
      screen.queryByRole("radio", { name: /pay at the shop/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("radio", { name: /pay online/i }),
    ).toBeInTheDocument();
  });

  it("offers paying at the shop when the platform has it on", () => {
    useHappyPathHandlers();
    renderPayStep({ cashAtStoreEnabled: true });

    expect(
      screen.getByRole("radio", { name: /pay at the shop/i }),
    ).toBeInTheDocument();
  });

  it("books the job and shows the code when paying at the shop", async () => {
    let simulateCalled = false;
    let sentMethod: string | null = null;
    server.use(
      http.post("/api/v1/orders", async ({ request }) => {
        const body = (await request.json()) as { payment_method?: string };
        sentMethod = body.payment_method ?? null;
        return HttpResponse.json(
          {
            order: cashOrder,
            payment: {
              provider: "cash",
              provider_order_id: "cash_order_1",
              amount_paise: 2000,
              currency: "INR",
              key_id: null,
            },
          },
          { status: 201 },
        );
      }),
      http.post("/api/v1/testing/simulate-payment", () => {
        simulateCalled = true;
        return HttpResponse.json({ status: "paid" });
      }),
    );
    const user = userEvent.setup();
    renderPayStep({
      paymentMethod: "at_store",
      cashAtStoreEnabled: true,
    });

    await user.click(screen.getByRole("button", { name: /reserve for/i }));

    expect(await screen.findByText("Reserved for you")).toBeInTheDocument();
    expect(screen.getByText("481902")).toBeInTheDocument();
    expect(screen.getByText(/₹20\.00/)).toBeInTheDocument();
    expect(sentMethod).toBe("at_store");
    // A cash order has no provider to wait for, so nothing is simulated.
    expect(simulateCalled).toBe(false);
  });

  it("tells the customer not to pay again when the payment is not confirmed", async () => {
    server.use(
      http.post("/api/v1/orders", () =>
        HttpResponse.json(
          {
            order: {
              ...order,
              status: "PENDING_PAYMENT",
              pickup_code: null,
            },
            payment: {
              provider: "fake",
              provider_order_id: "fake_order_1",
              amount_paise: 2000,
              currency: "INR",
              key_id: null,
            },
          },
          { status: 201 },
        ),
      ),
      http.post("/api/v1/testing/simulate-payment", () =>
        HttpResponse.json({ status: "refund_pending" }),
      ),
      http.get("/api/v1/orders/:id", () =>
        HttpResponse.json({
          order: { ...order, status: "PENDING_PAYMENT", pickup_code: null },
          events: [],
        }),
      ),
    );
    const user = userEvent.setup();
    renderPayStep();

    await user.click(screen.getByRole("button", { name: /pay/i }));

    await waitFor(
      () => expect(screen.getByText(/do not pay again/i)).toBeInTheDocument(),
      { timeout: 6000 },
    );
  });
});
