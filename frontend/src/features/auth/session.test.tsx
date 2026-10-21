import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { errorResponse, handlers } from "../../test/msw/handlers";
import { server } from "../../test/msw/server";
import { renderWithProviders } from "../../test/render";
import { useSession } from "./session";

function Probe() {
  const { status, user } = useSession();
  return (
    <div>
      <p role="status">status: {status}</p>
      <p>email: {user?.email ?? "none"}</p>
    </div>
  );
}

describe("the session", () => {
  it("is anonymous when there is no session at all", async () => {
    renderWithProviders(<Probe />, { signedIn: false });

    expect(await screen.findByText("status: anonymous")).toBeInTheDocument();
  });

  it("is the account when the server knows the token", async () => {
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

    renderWithProviders(<Probe />);

    expect(await screen.findByText("status: authenticated")).toBeInTheDocument();
    expect(screen.getByText("email: customer@example.com")).toBeInTheDocument();
  });

  it("needs onboarding when the token is good but there is no account", async () => {
    server.use(
      http.get("/api/v1/me", () =>
        errorResponse(
          403,
          "ACCOUNT_NOT_PROVISIONED",
          "This account has not been set up yet.",
        ),
      ),
    );

    renderWithProviders(<Probe />);

    expect(await screen.findByText("status: needs-onboarding")).toBeInTheDocument();
  });

  it("is anonymous when the token is refused", async () => {
    server.use(
      http.get("/api/v1/me", () =>
        errorResponse(401, "UNAUTHENTICATED", "Authentication required"),
      ),
    );

    renderWithProviders(<Probe />);

    expect(await screen.findByText("status: anonymous")).toBeInTheDocument();
  });
});

describe("the default handlers", () => {
  it("answer the account route with a refusal", async () => {
    const response = await fetch("/api/v1/me");
    expect(response.status).toBe(401);
  });

  it("are the ones the suite starts with", () => {
    expect(handlers.length).toBeGreaterThan(0);
  });
});

describe("the session and the account", () => {
  it("waits for the answer before it says anything", async () => {
    renderWithProviders(<Probe />);

    await waitFor(() =>
      expect(screen.getByRole("status")).not.toHaveTextContent("loading"),
    );
  });
});
