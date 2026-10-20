import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import { server } from "../../test/msw/server";
import { renderWithProviders } from "../../test/render";
import { GoogleButton } from "./google-button";
import { openExternal } from "./oauth-navigation";

vi.mock("./oauth-navigation", () => ({ openExternal: vi.fn() }));

describe("GoogleButton", () => {
  it("sends the browser to the address the server gives", async () => {
    server.use(
      http.post("/api/v1/auth/oauth/google/start", () =>
        HttpResponse.json({ url: "https://provider.example/authorize" }),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<GoogleButton />);

    await user.click(
      await screen.findByRole("button", { name: "Continue with Google" }),
    );

    expect(openExternal).toHaveBeenCalledWith(
      "https://provider.example/authorize",
    );
  });

  it("says so when the provider is not available on this deployment", async () => {
    server.use(
      http.post("/api/v1/auth/oauth/google/start", () =>
        HttpResponse.json(
          {
            error: {
              code: "OAUTH_PROVIDER_UNAVAILABLE",
              message: "not available",
              details: {},
              request_id: "req-1",
            },
          },
          { status: 400 },
        ),
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<GoogleButton />);

    await user.click(
      await screen.findByRole("button", { name: "Continue with Google" }),
    );

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Signing in with Google is not available on this deployment.",
    );
  });
});
