import { describe, expect, it } from "vitest";

import {
  formatPaise,
  formatPaiseForInput,
  isValidRupeesInput,
  parseRupeesToPaise,
} from "./money";

describe("formatPaise", () => {
  it("formats paise as rupees", () => {
    expect(formatPaise(1250)).toContain("12.50");
    expect(formatPaise(5)).toContain("0.05");
  });
});

describe("parseRupeesToPaise", () => {
  it("converts whole and decimal rupees to integer paise", () => {
    expect(parseRupeesToPaise("12.50")).toBe(1250);
    expect(parseRupeesToPaise("12.5")).toBe(1250);
    expect(parseRupeesToPaise("0.01")).toBe(1);
    expect(parseRupeesToPaise("3")).toBe(300);
  });

  it("trims whitespace", () => {
    expect(parseRupeesToPaise(" 2 ")).toBe(200);
  });

  it("rejects invalid or non-positive input", () => {
    expect(parseRupeesToPaise("")).toBeNull();
    expect(parseRupeesToPaise("0")).toBeNull();
    expect(parseRupeesToPaise("-5")).toBeNull();
    expect(parseRupeesToPaise("abc")).toBeNull();
    expect(parseRupeesToPaise("1.234")).toBeNull();
  });
});

describe("isValidRupeesInput", () => {
  it("accepts up to two decimal places", () => {
    expect(isValidRupeesInput("1")).toBe(true);
    expect(isValidRupeesInput("1.2")).toBe(true);
    expect(isValidRupeesInput("1.23")).toBe(true);
    expect(isValidRupeesInput("1.234")).toBe(false);
    expect(isValidRupeesInput("0")).toBe(false);
  });
});

describe("formatPaiseForInput", () => {
  it("renders zero as an empty input", () => {
    expect(formatPaiseForInput(0)).toBe("");
  });

  it("renders paise without trailing zeros", () => {
    expect(formatPaiseForInput(1500)).toBe("15");
    expect(formatPaiseForInput(1550)).toBe("15.5");
    expect(formatPaiseForInput(1505)).toBe("15.05");
    expect(formatPaiseForInput(123456)).toBe("1234.56");
  });
});
