import { screen } from "@testing-library/react";
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

const reservedOrder = {
  id: "22222222-2222-4222-8222-222222222222",
  order_no: 1042,
  status: "RESERVED",
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
  payment_method: "at_store",
  paid_at: null,
  created_at: "2026-01-01T00:09:00Z",
};

function renderPayStep() {
  return renderWithProviders(
    <PayStep
      upload={upload}
      options={options}
      shop={shop}
      quote={quote}
      onBack={() => undefined}
    />,
    { route: "/new" },
  );
}

describe("PayStep", () => {
  it("books the job and shows the pickup code", async () => {
    let sentBody: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/v1/orders", async ({ request }) => {
        sentBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ order: reservedOrder }, { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderPayStep();

    expect(
      screen.getByText(/pay ₹20\.00 in cash at the counter/i),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: /reserve for ₹20\.00/i }),
    );

    expect(await screen.findByText("Reserved for you")).toBeInTheDocument();
    expect(screen.getByText("481902")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View order" })).toHaveAttribute(
      "href",
      `/orders/${reservedOrder.id}`,
    );
    expect(sentBody).toMatchObject({
      upload_id: upload.id,
      shop_id: shop.id,
      expected_price_paise: 2000,
    });
    expect(sentBody).not.toHaveProperty("payment_method");
  });

  it("offers no way to pay online", () => {
    renderPayStep();

    expect(screen.queryAllByRole("radio")).toHaveLength(0);
    expect(screen.queryByText(/pay online/i)).not.toBeInTheDocument();
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

    await user.click(screen.getByRole("button", { name: /reserve for/i }));

    expect(
      await screen.findByText("This file is already attached to an order."),
    ).toBeInTheDocument();
  });
});
