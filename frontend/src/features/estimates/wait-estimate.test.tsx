import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { WaitEstimateResponse } from "../../api/client";
import { errorResponse } from "../../test/msw/handlers";
import { server } from "../../test/msw/server";
import { renderWithProviders } from "../../test/render";
import { ShopWaitEstimate, WaitEstimate } from "./wait-estimate";

const estimate: WaitEstimateResponse = {
  shop_id: "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa",
  minimum_minutes: 4.2,
  median_minutes: 6,
  maximum_minutes: 9.1,
  sample_count: 4,
  rough: true,
  algorithm_version: "1",
};

describe("WaitEstimate", () => {
  it("shows a whole-minute range and the rough evidence label", () => {
    renderWithProviders(<WaitEstimate estimate={estimate} />);

    expect(
      screen.getByText(/Current queue wait: 4–10 min/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Rough estimate · 4\/10 recent jobs/),
    ).toBeInTheDocument();
    expect(screen.getByText(/not a ready-time promise/)).toBeInTheDocument();
  });

  it("shows the empty queue as 0–0 without inventing work", () => {
    renderWithProviders(
      <WaitEstimate
        estimate={{
          ...estimate,
          minimum_minutes: 0,
          median_minutes: 0,
          maximum_minutes: 0,
          sample_count: 0,
        }}
      />,
    );

    expect(screen.getByText(/0–0 min/)).toBeInTheDocument();
    expect(screen.getByText(/No unfinished print work/)).toBeInTheDocument();
  });

  it("shows loading and unavailable states without raw errors", () => {
    const { rerender } = renderWithProviders(<WaitEstimate pending />);
    expect(screen.getByRole("status")).toHaveTextContent(
      /Checking current queue wait/,
    );
    rerender(<WaitEstimate estimate={null} />);
    expect(screen.getByRole("status")).toHaveTextContent(
      /unavailable right now/,
    );
  });
});

describe("ShopWaitEstimate", () => {
  it("loads the single-shop estimate and labels it as not this order's promise", async () => {
    server.use(
      http.get("/api/v1/shops/:id/wait-estimate", () =>
        HttpResponse.json({ ...estimate, sample_count: 12, rough: false }),
      ),
    );
    renderWithProviders(<ShopWaitEstimate shopId={estimate.shop_id} />);

    expect(
      await screen.findByText(/Current queue wait at this shop: 4–10 min/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Based on 12 recent print jobs/),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/not a promised start time for this order/),
    ).toBeInTheDocument();
  });

  it("offers a retry after an endpoint failure", async () => {
    let calls = 0;
    server.use(
      http.get("/api/v1/shops/:id/wait-estimate", () => {
        calls += 1;
        return calls === 1
          ? errorResponse(503, "UNAVAILABLE", "Database unavailable")
          : HttpResponse.json(estimate);
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<ShopWaitEstimate shopId={estimate.shop_id} />);

    expect(
      await screen.findByText(/unavailable right now/),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try again" }));

    expect(
      await screen.findByText(/Current queue wait at this shop/),
    ).toBeInTheDocument();
    expect(calls).toBe(2);
  });
});
