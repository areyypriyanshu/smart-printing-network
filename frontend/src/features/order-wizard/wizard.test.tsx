import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

type PositionCallback = (position: GeolocationPosition) => void;
type PositionErrorCallback = (error: GeolocationPositionError) => void;

import type {
  QuoteResponse,
  ShopResponse,
  UploadResponse,
} from "../../api/client";
import { errorResponse } from "../../test/msw/handlers";
import { server } from "../../test/msw/server";
import { renderWithProviders } from "../../test/render";
import { OrderWizardPage } from "./wizard";

const uploadFixture: UploadResponse = {
  id: "11111111-1111-4111-8111-111111111111",
  original_filename: "notes.pdf",
  page_count: 5,
  size_bytes: 2048,
  created_at: "2026-01-01T00:00:00Z",
};

const alpha: ShopResponse = {
  id: "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa",
  name: "Alpha Prints",
  address: "1 Main Street",
  latitude: 19.07,
  longitude: 72.87,
  min_order_paise: 0,
  rates: [{ paper_size: "A4", color: false, duplex: false, rate_paise: 200 }],
};

const beta: ShopResponse = {
  id: "bbbbbbbb-1111-4111-8111-bbbbbbbbbbbb",
  name: "Beta Print Hub",
  address: "2 Market Road",
  latitude: 19.08,
  longitude: 72.88,
  min_order_paise: 5000,
  rates: [{ paper_size: "A4", color: false, duplex: false, rate_paise: 500 }],
};

const gamma: ShopResponse = {
  id: "cccccccc-1111-4111-8111-cccccccccccc",
  name: "Gamma Copies",
  address: "3 Station Lane",
  latitude: 19.09,
  longitude: 72.89,
  min_order_paise: 0,
  rates: [],
};

function quoteFor(
  shop: ShopResponse,
  pricePaise: number,
  ratePaise: number,
): QuoteResponse {
  return {
    upload_id: uploadFixture.id,
    shop_id: shop.id,
    page_count: 5,
    copies: 1,
    rate_paise: ratePaise,
    min_order_paise: shop.min_order_paise,
    price_paise: pricePaise,
  };
}

function useWizardHandlers() {
  server.use(
    http.get("/api/v1/uploads/:id", () => HttpResponse.json(uploadFixture)),
    http.get("/api/v1/shops", () =>
      HttpResponse.json({ items: [alpha, beta, gamma], next_cursor: null }),
    ),
    http.post("/api/v1/quotes", async ({ request }) => {
      const body = (await request.json()) as { shop_id: string };
      if (body.shop_id === alpha.id)
        return HttpResponse.json(quoteFor(alpha, 1000, 200));
      if (body.shop_id === beta.id)
        return HttpResponse.json(quoteFor(beta, 5000, 500));
      return errorResponse(409, "RATE_NOT_SET", "No rate for these options");
    }),
  );
}

describe("OrderWizardPage", () => {
  it("rejects a file it cannot print before uploading", async () => {
    const user = userEvent.setup({ applyAccept: false });
    renderWithProviders(<OrderWizardPage />, { route: "/new" });

    const input = screen.getByLabelText(/drag a pdf/i);
    await user.upload(
      input,
      new File(["hello"], "notes.txt", { type: "text/plain" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /Download as PDF/i,
    );
  });

  it("accepts a Word document", async () => {
    useWizardHandlers();
    server.use(
      http.post("/api/v1/uploads", () =>
        HttpResponse.json(uploadFixture, { status: 201 }),
      ),
    );
    const user = userEvent.setup({ applyAccept: false });
    renderWithProviders(<OrderWizardPage />, { route: "/new" });

    const input = screen.getByLabelText(/drag a pdf/i);
    await user.upload(
      input,
      new File(["word"], "report.docx", {
        type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      }),
    );

    expect(await screen.findByText(/notes\.pdf/)).toBeInTheDocument();
  });

  it("rejects an empty file", async () => {
    const user = userEvent.setup();
    renderWithProviders(<OrderWizardPage />, { route: "/new" });

    const input = screen.getByLabelText(/drag a pdf/i);
    await user.upload(
      input,
      new File([], "empty.pdf", { type: "application/pdf" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "That file is empty.",
    );
  });

  it("uploads a PDF and shows its page count", async () => {
    useWizardHandlers();
    server.use(
      http.post("/api/v1/uploads", () =>
        HttpResponse.json(uploadFixture, { status: 201 }),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<OrderWizardPage />, { route: "/new" });

    const input = screen.getByLabelText(/drag a pdf/i);
    await user.upload(
      input,
      new File(["%PDF-1.4 test"], "notes.pdf", { type: "application/pdf" }),
    );

    expect(await screen.findByText(/notes\.pdf/)).toBeInTheDocument();
    expect(screen.getByText(/5 pages/)).toBeInTheDocument();
  });

  it("resumes a completed upload from the URL", async () => {
    useWizardHandlers();
    renderWithProviders(<OrderWizardPage />, {
      route: `/new?upload=${uploadFixture.id}`,
    });

    expect(
      await screen.findByRole("group", { name: "Paper size" }),
    ).toBeInTheDocument();
  });

  it("shows priced shops cheapest first, unavailable last, and the selection summary", async () => {
    useWizardHandlers();
    const user = userEvent.setup();
    renderWithProviders(<OrderWizardPage />, {
      route: `/new?upload=${uploadFixture.id}`,
    });

    await user.click(await screen.findByRole("button", { name: "Continue" }));

    expect(await screen.findByText("Alpha Prints")).toBeInTheDocument();
    expect(screen.getByText(/₹\s?10\.00/)).toBeInTheDocument();

    const betaItem = screen
      .getByRole("heading", { name: "Beta Print Hub" })
      .closest("li");
    expect(betaItem).not.toBeNull();
    expect(
      within(betaItem as HTMLElement).getAllByText(/₹\s?50\.00/),
    ).toHaveLength(2);
    expect(
      within(betaItem as HTMLElement).getByText("Minimum order applies."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Does not offer these options."),
    ).toBeInTheDocument();

    const names = screen
      .getAllByRole("heading", { level: 3 })
      .map((heading) => heading.textContent);
    expect(names).toEqual(["Alpha Prints", "Beta Print Hub", "Gamma Copies"]);

    await user.click(
      screen.getAllByRole("button", { name: "Choose this shop" })[0],
    );

    const selection = await screen.findByRole("region", {
      name: "Your selection",
    });
    expect(within(selection).getByText("Alpha Prints")).toBeInTheDocument();
    expect(within(selection).getByText(/₹\s?10\.00/)).toBeInTheDocument();
  });
});

describe("finding shops near me", () => {
  it("asks the browser for a location and shows the shops around it", async () => {
    useWizardHandlers();
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
    renderWithProviders(<OrderWizardPage />, {
      route: `/new?upload=${uploadFixture.id}`,
    });

    await user.click(await screen.findByRole("button", { name: "Continue" }));
    await user.click(
      await screen.findByRole("button", { name: /find shops near me/i }),
    );

    expect(getCurrentPosition).toHaveBeenCalled();
    expect(
      await screen.findByRole("button", { name: /showing shops near me/i }),
    ).toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it("carries on with every shop when the browser refuses the location", async () => {
    useWizardHandlers();
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
    renderWithProviders(<OrderWizardPage />, {
      route: `/new?upload=${uploadFixture.id}`,
    });

    await user.click(await screen.findByRole("button", { name: "Continue" }));
    await user.click(
      await screen.findByRole("button", { name: /find shops near me/i }),
    );

    expect(
      await screen.findByText(/could not find your location/i),
    ).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
