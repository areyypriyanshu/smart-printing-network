import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import {
  customerUser,
  errorResponse,
  vendorUser,
} from "../../test/msw/handlers";
import { server } from "../../test/msw/server";
import { renderWithProviders } from "../../test/render";
import { LoginPage } from "./login-page";

const accessTokenResponse = {
  access_token: "test-access-token",
  expires_in: 900,
  token_type: "bearer",
};

function renderLoginPage() {
  return renderWithProviders(
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<p>Customer home</p>} />
      <Route path="/vendor/rates" element={<p>Vendor rates</p>} />
    </Routes>,
    { route: "/login" },
  );
}

describe("LoginPage", () => {
  it("shows validation messages when submitted empty", async () => {
    const user = userEvent.setup();
    renderLoginPage();

    await user.click(await screen.findByRole("button", { name: "Sign in" }));

    expect(
      await screen.findByText("Enter a valid email address"),
    ).toBeInTheDocument();
    expect(screen.getByText("Enter your password")).toBeInTheDocument();
  });

  it("toggles password visibility", async () => {
    const user = userEvent.setup();
    renderLoginPage();

    const password = await screen.findByLabelText("Password");
    expect(password).toHaveAttribute("type", "password");

    await user.click(screen.getByRole("button", { name: "Show password" }));
    expect(password).toHaveAttribute("type", "text");

    await user.click(screen.getByRole("button", { name: "Hide password" }));
    expect(password).toHaveAttribute("type", "password");
  });

  it("shows an alert for wrong credentials", async () => {
    server.use(
      http.post("/api/v1/auth/login", () =>
        errorResponse(401, "UNAUTHENTICATED", "Invalid email or password."),
      ),
    );
    const user = userEvent.setup();
    renderLoginPage();

    await user.type(
      await screen.findByLabelText("Email"),
      "vendor@example.com",
    );
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Invalid email or password.",
    );
  });

  it("sends a customer to the home page after login", async () => {
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json(accessTokenResponse),
      ),
      http.get("/api/v1/me", () => HttpResponse.json(customerUser)),
    );
    const user = userEvent.setup();
    renderLoginPage();

    await user.type(
      await screen.findByLabelText("Email"),
      "customer@example.com",
    );
    await user.type(screen.getByLabelText("Password"), "password-123");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Customer home")).toBeInTheDocument();
  });

  it("sends a vendor to the rates page after login", async () => {
    server.use(
      http.post("/api/v1/auth/login", () =>
        HttpResponse.json(accessTokenResponse),
      ),
      http.get("/api/v1/me", () => HttpResponse.json(vendorUser)),
    );
    const user = userEvent.setup();
    renderLoginPage();

    await user.type(
      await screen.findByLabelText("Email"),
      "vendor@example.com",
    );
    await user.type(screen.getByLabelText("Password"), "password-123");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Vendor rates")).toBeInTheDocument();
  });
});
