import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "../../test/render";
import { CheckEmailPage } from "./check-email-page";

describe("CheckEmailPage", () => {
  it("says where the link went", async () => {
    renderWithProviders(
      <Routes>
        <Route path="/check-your-email" element={<CheckEmailPage />} />
      </Routes>,
      {
        route: "/check-your-email",
        // The address is passed in the state of the navigation, so that
        // it never lands in the address bar or in a log.
        state: { email: "customer@example.com" },
      },
    );

    expect(await screen.findByText("customer@example.com")).toBeInTheDocument();
  });

  it("says where to go when the address was wrong", async () => {
    renderWithProviders(
      <Routes>
        <Route path="/check-your-email" element={<CheckEmailPage />} />
        <Route path="/account/email" element={<p>Change the address</p>} />
      </Routes>,
      { route: "/check-your-email", state: { email: "customer@example.com" } },
    );

    expect(
      await screen.findByRole("link", {
        name: "Use a different email address",
      }),
    ).toBeInTheDocument();
  });
});
