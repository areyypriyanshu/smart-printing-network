import { describe, expect, it } from "vitest";

import { pickupMessage, pickupShareLink, whatsappLink } from "./share";

describe("sharing the pickup code", () => {
  it("opens WhatsApp with the message already written", () => {
    const link = whatsappLink("hello there");

    expect(link).toBe("https://wa.me/?text=hello%20there");
  });

  it("says which order it is and what the code is", () => {
    const message = pickupMessage({
      order_no: 1042,
      pickup_code: "481902",
      shopName: "Central Prints",
    });

    expect(message).toContain("481902");
    expect(message).toContain("1042");
    expect(message).toContain("Central Prints");
  });

  it("works without a shop name", () => {
    const message = pickupMessage({
      order_no: 1042,
      pickup_code: "481902",
    });

    expect(message).toContain("481902");
    expect(message).not.toContain("undefined");
  });

  it("puts the code in the link", () => {
    const link = pickupShareLink({
      order_no: 1042,
      pickup_code: "481902",
      shopName: "Central Prints",
    });

    expect(link.startsWith("https://wa.me/?text=")).toBe(true);
    expect(decodeURIComponent(link.split("text=")[1])).toContain("481902");
  });
});
