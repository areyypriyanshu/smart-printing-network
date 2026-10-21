import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import { server } from "../../test/msw/server";
import { renderWithProviders } from "../../test/render";
import { OnboardingPage } from "./onboarding-page";

function renderOnboarding() {
  return renderWithProviders(
    <Routes>
      <Route path="/onboarding" element={<OnboardingPage />} />
      <Route path="/" element={<p>Home</p>} />
    </Routes>,
    { route: "/onboarding" },
  );
}

describe("the onboarding page", () => {
  it("asks what the person is here for", async () => {
    renderOnboarding();

    expect(
      await screen.findByText(/what are you here for/i),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/print something/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/run a print shop/i)).toBeInTheDocument();
  });

  it("does not ask for a shop from somebody who is here to print", async () => {
    renderOnboarding();

    await screen.findByLabelText(/print something/i);

    expect(screen.queryByLabelText(/shop name/i)).not.toBeInTheDocument();
  });

  it("asks for the shop when the person runs one", async () => {
    const user = userEvent.setup();
    renderOnboarding();

    await user.click(await screen.findByLabelText(/run a print shop/i));

    expect(await screen.findByLabelText(/shop name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/shop address/i)).toBeInTheDocument();
  });

  it("refuses a shop with no name", async () => {
    const user = userEvent.setup();
    renderOnboarding();

    await user.click(await screen.findByLabelText(/run a print shop/i));
    await user.click(await screen.findByRole("button", { name: /continue/i }));

    expect(await screen.findByText(/enter the shop name/i)).toBeInTheDocument();
  });

  it("tells the server the intent and nothing else", async () => {
    const user = userEvent.setup();
    let body: unknown = null;
    server.use(
      http.post("/api/v1/auth/onboarding", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          id: "8fd2dc7c-2f2e-4d70-9f5e-bc1a0c8a1a11",
          email: "customer@example.com",
          full_name: "Customer One",
          role: "customer",
          created_at: "2026-01-01T00:00:00Z",
        });
      }),
      http.get("/api/v1/me", () =>
        HttpResponse.json({
          id: "8fd2dc7c-2f2e-4d70-9f5e-bc1a0c8a1a11",
          email: "customer@example.com",
          full_name: "Customer One",
          role: "customer",
          created_at: "2026-01-01T00:00:00Z",
        }),
      ),
    );
    renderOnboarding();

    await user.click(await screen.findByRole("button", { name: /continue/i }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toEqual({ role: "customer" });
  });
});
