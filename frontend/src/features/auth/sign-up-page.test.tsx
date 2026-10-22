import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../../test/render";
import { readIntent, SHOP } from "./intent";
import { SignUpPage } from "./sign-up-page";

// The provider's own sign up is a component of theirs, and it needs
// their provider around it. What this page does with the reason is
// ours, so the provider's part is stood in for.
vi.mock("@clerk/react", () => ({
  SignUp: () => <p>the provider's sign up</p>,
}));

/**
 * The sign up, and the reason a person gave before it.
 *
 * The identity provider's sign up happens in between: the person leaves
 * for the provider and comes back, and the reason has to survive the
 * trip. It is carried in the address of the link and kept here.
 */
function renderSignUp(route: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/register" element={<SignUpPage />} />
    </Routes>,
    { route },
  );
}

describe("the sign up page", () => {
  it("keeps the reason the link carried", async () => {
    renderSignUp("/register?as=shop");

    await screen.findByRole("heading", { name: /create an account/i });

    expect(readIntent()).toBe(SHOP);
  });

  it("keeps no reason when the link carried none", async () => {
    renderSignUp("/register");

    await screen.findByRole("heading", { name: /create an account/i });

    expect(readIntent()).toBeNull();
  });
});
