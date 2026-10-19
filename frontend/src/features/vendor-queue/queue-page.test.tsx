import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { errorResponse } from "../../test/msw/handlers";
import { server } from "../../test/msw/server";
import { renderWithProviders } from "../../test/render";
import { VendorQueuePage } from "./queue-page";

type QueueItem = {
  id: string;
  order_no: number;
  status: string;
  status_reason: string | null;
  upload_id: string;
  page_count: number;
  copies: number;
  paper_size: string;
  color: boolean;
  duplex: boolean;
  price_paise: number;
  paid_at: string | null;
  created_at: string;
};

function item(overrides: Partial<QueueItem> = {}): QueueItem {
  return {
    id: "11111111-1111-4111-8111-111111111111",
    order_no: 42,
    status: "PAID",
    status_reason: null,
    upload_id: "22222222-2222-4222-8222-222222222222",
    page_count: 24,
    copies: 2,
    paper_size: "A4",
    color: true,
    duplex: false,
    price_paise: 3840,
    paid_at: new Date(Date.now() - 3 * 60_000).toISOString(),
    created_at: new Date().toISOString(),
    ...overrides,
  };
}

function useQueueHandlers(items: QueueItem[]) {
  server.use(
    http.get("/api/v1/vendor/queue", () =>
      HttpResponse.json({ items, accept_timeout_minutes: 15 }),
    ),
  );
}

describe("VendorQueuePage", () => {
  it("shows the four columns with their counts", async () => {
    useQueueHandlers([item()]);
    renderWithProviders(<VendorQueuePage />, { route: "/vendor" });

    const newColumn = await screen.findByRole("region", { name: "New" });
    expect(within(newColumn).getByText("1")).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Accepted" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Printing" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Ready" })).toBeInTheDocument();
  });

  it("shows an empty state when nothing is waiting", async () => {
    useQueueHandlers([]);
    renderWithProviders(<VendorQueuePage />, { route: "/vendor" });

    expect(
      await screen.findByText(/nothing waiting right now/i),
    ).toBeInTheDocument();
  });

  it("puts each order in the column for its status", async () => {
    useQueueHandlers([
      item({ id: "a", order_no: 1, status: "PAID" }),
      item({ id: "b", order_no: 2, status: "ACCEPTED" }),
      item({ id: "c", order_no: 3, status: "PRINTING" }),
      item({ id: "d", order_no: 4, status: "READY" }),
    ]);
    renderWithProviders(<VendorQueuePage />, { route: "/vendor" });

    const newColumn = await screen.findByRole("region", { name: "New" });
    const acceptedColumn = screen.getByRole("region", { name: "Accepted" });
    const printingColumn = screen.getByRole("region", { name: "Printing" });
    const readyColumn = screen.getByRole("region", { name: "Ready" });

    expect(within(newColumn).getByText("#1")).toBeInTheDocument();
    expect(within(acceptedColumn).getByText("#2")).toBeInTheDocument();
    expect(within(printingColumn).getByText("#3")).toBeInTheDocument();
    expect(within(readyColumn).getByText("#4")).toBeInTheDocument();
  });

  it("shows the print options on the card", async () => {
    useQueueHandlers([item()]);
    renderWithProviders(<VendorQueuePage />, { route: "/vendor" });

    expect(await screen.findByText(/24 pages × 2 copies/)).toBeInTheDocument();
    expect(screen.getByText(/A4 · Colour · Single sided/)).toBeInTheDocument();
  });

  it("warns when a new order is close to the auto reject limit", async () => {
    useQueueHandlers([
      item({ paid_at: new Date(Date.now() - 13 * 60_000).toISOString() }),
    ]);
    renderWithProviders(<VendorQueuePage />, { route: "/vendor" });

    expect(
      await screen.findByText(/auto reject in 2 minutes/i),
    ).toBeInTheDocument();
  });

  it("does not warn about an order that has just been paid", async () => {
    useQueueHandlers([item()]);
    renderWithProviders(<VendorQueuePage />, { route: "/vendor" });

    await screen.findByText("#42");
    expect(screen.queryByText(/auto reject in/i)).not.toBeInTheDocument();
  });

  it("accepts an order", async () => {
    const calls: string[] = [];
    useQueueHandlers([item()]);
    server.use(
      http.post("/api/v1/vendor/orders/:id/accept", ({ params }) => {
        calls.push(String(params.id));
        return HttpResponse.json(item({ status: "ACCEPTED" }));
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<VendorQueuePage />, { route: "/vendor" });

    await user.click(await screen.findByRole("button", { name: "Accept" }));

    expect(calls).toHaveLength(1);
  });

  it("refuses to reject an order without a reason", async () => {
    useQueueHandlers([item()]);
    const user = userEvent.setup();
    renderWithProviders(<VendorQueuePage />, { route: "/vendor" });

    await user.click(await screen.findByRole("button", { name: "Reject" }));
    await user.click(screen.getByRole("button", { name: "Reject order" }));

    expect(
      await screen.findByText(/give the customer a reason/i),
    ).toBeInTheDocument();
  });

  it("sends the reason when rejecting", async () => {
    let body: unknown = null;
    useQueueHandlers([item()]);
    server.use(
      http.post("/api/v1/vendor/orders/:id/reject", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(item({ status: "REJECTED" }));
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<VendorQueuePage />, { route: "/vendor" });

    await user.click(await screen.findByRole("button", { name: "Reject" }));
    await user.type(screen.getByLabelText("Reason"), "Out of colour toner");
    await user.click(screen.getByRole("button", { name: "Reject order" }));

    expect(body).toEqual({ reason: "Out of colour toner" });
  });

  it("asks for the pickup code before handing an order over", async () => {
    let body: unknown = null;
    useQueueHandlers([item({ status: "READY" })]);
    server.use(
      http.post("/api/v1/vendor/orders/:id/collect", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(item({ status: "COLLECTED" }));
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<VendorQueuePage />, { route: "/vendor" });

    await user.click(
      await screen.findByRole("button", { name: "Verify pickup" }),
    );
    await user.type(screen.getByLabelText("Pickup code"), "123456");
    await user.click(screen.getByRole("button", { name: "Hand over" }));

    expect(body).toEqual({ code: "123456" });
  });

  it("refuses a pickup code that is not six digits", async () => {
    useQueueHandlers([item({ status: "READY" })]);
    const user = userEvent.setup();
    renderWithProviders(<VendorQueuePage />, { route: "/vendor" });

    await user.click(
      await screen.findByRole("button", { name: "Verify pickup" }),
    );
    await user.type(screen.getByLabelText("Pickup code"), "12");
    await user.click(screen.getByRole("button", { name: "Hand over" }));

    expect(
      await screen.findByText(/enter the six digit code/i),
    ).toBeInTheDocument();
  });

  it("shows the server message when a code is wrong", async () => {
    useQueueHandlers([item({ status: "READY" })]);
    server.use(
      http.post("/api/v1/vendor/orders/:id/collect", () =>
        errorResponse(400, "PICKUP_CODE_INVALID", "Code does not match"),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<VendorQueuePage />, { route: "/vendor" });

    await user.click(
      await screen.findByRole("button", { name: "Verify pickup" }),
    );
    await user.type(screen.getByLabelText("Pickup code"), "000000");
    await user.click(screen.getByRole("button", { name: "Hand over" }));

    expect(await screen.findByText(/code does not match/i)).toBeInTheDocument();
  });

  it("shows an error state and a retry when the queue cannot be loaded", async () => {
    server.use(
      http.get("/api/v1/vendor/queue", () =>
        errorResponse(500, "INTERNAL_ERROR", "Something went wrong"),
      ),
    );
    renderWithProviders(<VendorQueuePage />, { route: "/vendor" });

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Try again" }),
    ).toBeInTheDocument();
  });
});
