import { describe, expect, it } from "vitest";

import { ApiError } from "../api/client";
import { fieldErrorsFor, messageForError } from "./errors";

describe("messageForError", () => {
  it("maps known API error codes to messages", () => {
    const error = new ApiError(401, "UNAUTHENTICATED", "nope", {}, null);
    expect(messageForError(error)).toBe("Invalid email or password.");
  });

  it("includes the request id for unknown codes", () => {
    const error = new ApiError(500, "SOMETHING_NEW", "boom", {}, "req-123");
    expect(messageForError(error)).toBe(
      "Something went wrong. Reference: req-123.",
    );
  });

  it("handles non-API errors", () => {
    expect(messageForError(new Error("network"))).toContain(
      "Check your connection",
    );
  });
});

describe("fieldErrorsFor", () => {
  it("maps validation details to field names", () => {
    const error = new ApiError(
      422,
      "VALIDATION_ERROR",
      "Request validation failed",
      { fields: [{ loc: ["body", "email"], msg: "not an email" }] },
      null,
    );
    expect(fieldErrorsFor(error)).toEqual({ email: "not an email" });
  });

  it("returns nothing for other error codes", () => {
    const error = new ApiError(409, "EMAIL_TAKEN", "taken", {}, null);
    expect(fieldErrorsFor(error)).toEqual({});
  });
});
