import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { ApiError, apiRequest } from "../../api/client";
import { errorResponse } from "../../test/msw/handlers";
import { server } from "../../test/msw/server";
import { renderWithProviders } from "../../test/render";
import { SessionProvider, useSession } from "./session";

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

    expect(
      await screen.findByText("status: authenticated"),
    ).toBeInTheDocument();
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

    expect(
      await screen.findByText("status: needs-onboarding"),
    ).toBeInTheDocument();
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

describe("a session that goes away", () => {
  it("does not change the state after it is gone", async () => {
    // The answer arrives after an await, and the screen can be gone by
    // then. Writing the answer to a component that is no longer on the
    // page is a change to nothing, and once the test file is finished
    // and the page is torn down it is an error the runner reports as a
    // failure of the file.
    let release: (token: string | null) => void = () => {};
    const answer = new Promise<string | null>((resolve) => {
      release = resolve;
    });

    const { unmount } = render(
      <SessionProvider
        getToken={() => answer}
        signOut={async () => {}}
        signedIn
        loaded
      >
        <Probe />
      </SessionProvider>,
    );

    // The screen goes while the answer is still on its way.
    unmount();
    release("test-token");
    await answer;

    // Let the answer land on a provider that is no longer there.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByText("status: authenticated")).toBeNull();
  });
});

describe("a caller with no token", () => {
  it("is refused by the account route", async () => {
    // The request goes through the API client, which is the way the
    // application makes it, and the token source is empty, so the
    // request carries no token at all.
    const error = await apiRequest("/me").then(
      () => null,
      (caught: unknown) => caught,
    );

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(401);
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
