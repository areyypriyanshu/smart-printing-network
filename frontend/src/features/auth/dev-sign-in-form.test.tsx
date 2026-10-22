import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "../../test/render";
import { DevSignInForm } from "./dev-sign-in-form";
import { DevSession } from "./dev-session";

/**
 * The local way in, which is the way a person walks locally.
 *
 * The registration form asks the browser where the shop is, the same
 * way the real sign up does, so that the owner does not have to look
 * a latitude and a longitude up.
 */
function renderTheForm() {
  return renderWithProviders(
    <DevSession>
      <DevSignInForm />
    </DevSession>,
    { route: "/login" },
  );
}

describe("the local way in", () => {
  it("takes the shop's place from the browser", async () => {
    const getCurrentPosition = vi.fn(
      (success: (position: GeolocationPosition) => void) => {
        success({
          coords: { latitude: 22.5726, longitude: 88.3639 },
        } as GeolocationPosition);
      },
    );
    vi.stubGlobal("navigator", {
      ...navigator,
      geolocation: { getCurrentPosition },
    });
    const user = userEvent.setup();
    renderTheForm();

    // The shop's fields are only there when the person came to
    // register a shop.
    expect(
      screen.queryByRole("button", { name: /use my current location/i }),
    ).not.toBeInTheDocument();

    renderWithProviders(
      <DevSession>
        <DevSignInForm />
      </DevSession>,
      { route: "/login?as=shop" },
    );

    await user.click(
      await screen.findByRole("button", { name: /use my current location/i }),
    );

    await waitFor(() =>
      expect(screen.getByLabelText(/latitude/i)).toHaveValue("22.572600"),
    );
    expect(screen.getByLabelText(/longitude/i)).toHaveValue("88.363900");
    vi.unstubAllGlobals();
  });

  it("says so when the browser will not share a location", async () => {
    const getCurrentPosition = vi.fn(
      (
        _success: (position: GeolocationPosition) => void,
        failure?: ((error: GeolocationPositionError) => void) | null,
      ) =>
        failure?.({ code: 1, message: "denied" } as GeolocationPositionError),
    );
    vi.stubGlobal("navigator", {
      ...navigator,
      geolocation: { getCurrentPosition },
    });
    const user = userEvent.setup();
    renderWithProviders(
      <DevSession>
        <DevSignInForm />
      </DevSession>,
      { route: "/login?as=shop" },
    );

    await user.click(
      await screen.findByRole("button", { name: /use my current location/i }),
    );

    expect(
      await screen.findByText(/could not find your location/i),
    ).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
