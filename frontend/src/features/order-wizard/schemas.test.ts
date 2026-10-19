import { describe, expect, it } from "vitest";

import { OPTION_DEFAULTS, describeOptions, optionsSchema } from "./schemas";

describe("optionsSchema", () => {
  it("accepts the defaults", () => {
    expect(optionsSchema.parse(OPTION_DEFAULTS)).toEqual(OPTION_DEFAULTS);
  });

  it("coerces the copies string from the input", () => {
    const parsed = optionsSchema.parse({ ...OPTION_DEFAULTS, copies: "12" });
    expect(parsed.copies).toBe(12);
  });

  it("rejects zero, negative, fractional and oversized copies", () => {
    for (const copies of [0, -1, 1.5, 101]) {
      const result = optionsSchema.safeParse({ ...OPTION_DEFAULTS, copies });
      expect(result.success).toBe(false);
    }
  });

  it("rejects an unknown paper size", () => {
    const result = optionsSchema.safeParse({
      ...OPTION_DEFAULTS,
      paper_size: "A2",
    });
    expect(result.success).toBe(false);
  });
});

describe("describeOptions", () => {
  it("describes a single-copy black and white job", () => {
    expect(describeOptions(OPTION_DEFAULTS)).toBe(
      "A4 · black and white · single-sided · 1 copy",
    );
  });

  it("describes a multi-copy colour duplex job", () => {
    expect(
      describeOptions({
        paper_size: "A3",
        color: true,
        duplex: true,
        copies: 4,
      }),
    ).toBe("A3 · colour · double-sided · 4 copies");
  });
});
