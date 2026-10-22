import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import { errorResponse } from "../../test/msw/handlers";
import { server } from "../../test/msw/server";
import { renderWithProviders } from "../../test/render";
import { RequireAuth, SendToOnboarding } from "./guards";

function renderGuarded() {
  return renderWithProviders(
    <Routes>
      <Route
        path="/"
        element={
          <RequireAuth>
            <p>The account</p>
          </RequireAuth>
        }
      />
      <Route path="/login" element={<p>Sign in</p>} />
      <Route path="/onboarding" element={<p>Choose what you are here for</p>} />
    </Routes>,
    { route: "/" },
  );
}

describe("the guard on the pages that need an account", () => {
  it("sends an anonymous visitor to the sign in page", async () => {
    renderGuarded();

    expect(await screen.findByText("Sign in")).toBeInTheDocument();
  });

  it("sends a person with no account to the page that asks", async () => {
    server.use(
      http.get("/api/v1/me", () =>
        errorResponse(
          403,
          "ACCOUNT_NOT_PROVISIONED",
          "This account has not been set up yet.",
        ),
      ),
    );
    renderGuarded();

    expect(
      await screen.findByText("Choose what you are here for"),
    ).toBeInTheDocument();
  });

  it("lets a person with an account through", async () => {
    server.use(
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
    renderGuarded();

    expect(await screen.findByText("The account")).toBeInTheDocument();
  });
});

function renderLanding() {
  return renderWithProviders(
    <Routes>
      <Route
        path="/"
        element={
          <SendToOnboarding>
            <p>The front page</p>
          </SendToOnboarding>
        }
      />
      <Route path="/onboarding" element={<p>Choose what you are here for</p>} />
    </Routes>,
    { route: "/" },
  );
}

describe("the landing page, for a person who has signed in", () => {
  it("asks a person with no account what they are here for", async () => {
    // A person who signs in lands on the front page, and there is
    // nothing they can do until they have said what they are here for.
    server.use(
      http.get("/api/v1/me", () =>
        errorResponse(
          403,
          "ACCOUNT_NOT_PROVISIONED",
          "This account has not been set up yet.",
        ),
      ),
    );
    renderLanding();

    expect(
      await screen.findByText("Choose what you are here for"),
    ).toBeInTheDocument();
  });

  it("leaves a person with an account on the front page", async () => {
    server.use(
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
    renderLanding();

    expect(await screen.findByText("The front page")).toBeInTheDocument();
  });
});
