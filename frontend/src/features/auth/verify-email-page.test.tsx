import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import { customerUser, errorResponse } from "../../test/msw/handlers";
import { server } from "../../test/msw/server";
import { renderWithProviders } from "../../test/render";
import { VerifyEmailPage } from "./verify-email-page";

function renderVerifyPage(route: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/verify-email" element={<VerifyEmailPage />} />
    </Routes>,
    { route },
  );
}

describe("VerifyEmailPage", () => {
  it("proves the address from the token in the link", async () => {
    let sent: unknown = null;
    server.use(
      http.post("/api/v1/auth/verify-email", async ({ request }) => {
        sent = await request.json();
        return HttpResponse.json({ ...customerUser, email_verified: true });
      }),
      http.get("/api/v1/me", () =>
        HttpResponse.json({ ...customerUser, email_verified: true }),
      ),
    );
    renderVerifyPage("/verify-email?token=a-token");

    expect(
      await screen.findByText(/Your email address is confirmed/),
    ).toBeInTheDocument();
    expect(sent).toEqual({ token: "a-token" });
  });

  it("says so when the link is not one the server sent", async () => {
    server.use(
      http.post("/api/v1/auth/verify-email", () =>
        errorResponse(
          400,
          "INVALID_VERIFICATION_TOKEN",
          "This link is not valid any more. Ask for a new one and try again.",
        ),
      ),
    );
    renderVerifyPage("/verify-email?token=stale");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This link is not valid any more.",
    );
  });

  it("says so when the link has no token in it", async () => {
    renderVerifyPage("/verify-email");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This link is not valid any more.",
    );
  });
});
