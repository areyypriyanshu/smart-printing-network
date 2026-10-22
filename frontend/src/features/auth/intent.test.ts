import { describe, expect, it } from "vitest";

import {
  forgetIntent,
  intentFromQuery,
  readIntent,
  rememberIntent,
  SHOP,
} from "./intent";

/**
 * The reason a person gave before they had an account.
 *
 * The reason is kept in the browser's own storage because the identity
 * provider's sign up happens in between, and the reason has to survive
 * the trip.
 */
describe("the reason a person gave", () => {
  it("is the shop when the link says so", () => {
    expect(intentFromQuery("shop")).toBe(SHOP);
  });

  it("is nothing when the link says anything else", () => {
    expect(intentFromQuery("customer")).toBeNull();
    expect(intentFromQuery("")).toBeNull();
    expect(intentFromQuery(null)).toBeNull();
  });

  it("survives the trip to the identity provider and back", () => {
    rememberIntent(SHOP);

    expect(readIntent()).toBe(SHOP);
  });

  it("is gone once it has been used", () => {
    rememberIntent(SHOP);
    forgetIntent();

    expect(readIntent()).toBeNull();
  });

  it("is nothing when it was never given", () => {
    expect(readIntent()).toBeNull();
  });
});
