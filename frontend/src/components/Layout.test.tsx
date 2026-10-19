import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "../test/render";
import { Layout } from "./Layout";

function renderLayout() {
  return renderWithProviders(
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<p>Home</p>} />
        <Route path="/login" element={<p>Login page</p>} />
      </Route>
    </Routes>,
    { route: "/" },
  );
}

describe("Layout", () => {
  it("offers a skip link and an accessible mobile menu", async () => {
    const user = userEvent.setup();
    renderLayout();

    expect(
      screen.getByRole("link", { name: "Skip to content" }),
    ).toHaveAttribute("href", "#main-content");
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");

    await user.click(await screen.findByRole("button", { name: "Open menu" }));

    expect(screen.getByRole("button", { name: "Close menu" })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
    expect(screen.getAllByRole("link", { name: "Sign in" })).toHaveLength(2);

    await user.click(screen.getAllByRole("link", { name: "Sign in" })[1]);

    expect(await screen.findByText("Login page")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Close menu" }),
    ).not.toBeInTheDocument();
  });
});
