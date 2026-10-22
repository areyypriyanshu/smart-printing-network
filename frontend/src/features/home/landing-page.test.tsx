import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { renderWithProviders } from "../../test/render";
import { LandingPage } from "./landing-page";

/**
 * The links on the front page.
 *
 * A link to a page that is not there is the quietest kind of mistake:
 * the person who follows it is told "page not found" and has no way of
 * knowing that the link was the problem and not the page. The route
 * that served a shop registration was removed when the identity
 * provider took the sign in, and the link to it stayed.
 */
describe("the front page", () => {
  it("sends a person who wants to run a shop to the sign up, saying so", () => {
    renderWithProviders(<LandingPage />);

    // The sign up is where an account begins, and the account is where
    // a person says they run a shop. The link says they are here for
    // the shop, so that they are not asked again.
    expect(
      screen.getAllByRole("link", { name: "Register your shop" })[0],
    ).toHaveAttribute("href", "/register?as=shop");
  });

  it("has no link to a page that is not served", () => {
    renderWithProviders(<LandingPage />);

    const links = screen.getAllByRole("link");
    expect(links.length).toBeGreaterThan(0);
    for (const link of links) {
      const href = link.getAttribute("href") ?? "";
      if (!href.startsWith("/")) continue;
      // The routes the application serves. A link to anything else is
      // a link to a page that is not there. The address a link carries
      // says why the person is going there, and not where, so the
      // question is about the path.
      const path = href.split("?")[0];
      expect([
        "/",
        "/login",
        "/register",
        "/new",
        "/onboarding",
        "/orders",
        "/vendor",
        "/vendor/rates",
        "/vendor/settings",
        "/admin/shops",
      ]).toContain(path);
    }
  });
});
