import { ApiError } from "../api/client";

const MESSAGES: Record<string, string> = {
  EMAIL_TAKEN: "An account with this email already exists.",
  UNAUTHENTICATED: "Invalid email or password.",
  FORBIDDEN: "You do not have access to this page.",
  NOT_FOUND: "We could not find what you asked for.",
  VALIDATION_ERROR: "Please check the highlighted fields.",
  RATE_LIMITED: "Too many attempts. Please wait a few minutes.",
  CONFLICT: "This was just updated elsewhere. Refresh and try again.",
  FILE_NOT_PDF: "That file is not a PDF.",
  FILE_TOO_LARGE: "The file is larger than 50 MB.",
  PDF_ENCRYPTED:
    "This PDF is password protected. Remove the password and try again.",
  PDF_CORRUPT: "We could not read this PDF.",
  PDF_TOO_MANY_PAGES: "This PDF has more than 300 pages.",
  PRICE_CHANGED: "The price changed. Review the new price.",
  SHOP_UNAVAILABLE: "This shop is not taking orders right now.",
  RATE_NOT_SET: "This shop does not offer those options.",
  PICKUP_CODE_INVALID: "Code does not match.",
};

export function messageForError(error: unknown): string {
  if (error instanceof ApiError) {
    const message = MESSAGES[error.code];
    if (message !== undefined) return message;
    return `Something went wrong. Reference: ${error.requestId ?? "unavailable"}.`;
  }
  return "Something went wrong. Check your connection and try again.";
}

export function fieldErrorsFor(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError) || error.code !== "VALIDATION_ERROR")
    return {};
  const details = error.details as {
    fields?: Array<{ loc?: unknown[]; msg?: string }>;
  } | null;
  const fields: Record<string, string> = {};
  for (const item of details?.fields ?? []) {
    const name = item.loc?.filter((part) => part !== "body").at(-1);
    if (typeof name === "string" && typeof item.msg === "string") {
      fields[name] = item.msg;
    }
  }
  return fields;
}
