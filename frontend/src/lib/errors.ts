import { ApiError } from "../api/client";

const MESSAGES: Record<string, string> = {
  EMAIL_TAKEN: "An account with this email already exists.",
  EMAIL_NOT_VERIFIED:
    "Confirm your email address first. We sent you a link when you signed up.",
  INVALID_VERIFICATION_TOKEN:
    "This link is not valid any more. Ask for a new one and try again.",
  PASSWORD_MISMATCH: "That password is not right.",
  OAUTH_ACCOUNT_EXISTS:
    "There is already an account with that email address. Sign in with your password and connect Google from your account.",
  OAUTH_STATE_INVALID: "That sign in did not work. Try again.",
  OAUTH_PROVIDER_UNAVAILABLE:
    "Signing in with Google is not available on this deployment.",
  OAUTH_PROVIDER_ERROR: "Google could not be reached. Try again in a moment.",
  UNAUTHENTICATED: "Invalid email or password.",
  FORBIDDEN: "You do not have access to this page.",
  NOT_FOUND: "We could not find what you asked for.",
  VALIDATION_ERROR: "Please check the highlighted fields.",
  RATE_LIMITED: "Too many attempts. Please wait a few minutes.",
  CONFLICT: "This was just updated elsewhere. Refresh and try again.",
  FILE_NOT_PDF:
    "We print PDF files. Open your file in Google Docs, choose File, " +
    "Download as PDF, then upload that.",
  FILE_TOO_LARGE: "The file is larger than 50 MB.",
  PDF_ENCRYPTED:
    "This PDF is password protected. Remove the password and try again.",
  PDF_CORRUPT: "We could not read this PDF.",
  PDF_TOO_MANY_PAGES: "This PDF has more than 300 pages.",
  PRICE_CHANGED: "The price changed. Review the new price.",
  SHOP_UNAVAILABLE: "This shop is not taking orders right now.",
  RATE_NOT_SET: "This shop does not offer those options.",
  PICKUP_CODE_INVALID: "Code does not match.",
  UPLOAD_ALREADY_USED: "This file is already attached to an order.",
  FILE_UNAVAILABLE:
    "This file is no longer stored, so it cannot be printed again. " +
    "Upload it once more and we will print it again.",
  INVALID_TRANSITION: "This order cannot change at this point.",
  SHOP_ALREADY_VERIFIED: "This shop is already approved and taking orders.",
  SHOP_NOT_VERIFIED:
    "This shop was never approved, so there is nothing to suspend.",
  PAYMENT_GATEWAY_ERROR:
    "The payment provider could not start the payment. Try again shortly.",
  WEBHOOK_SIGNATURE_INVALID: "The payment notification could not be verified.",
};

/** The message for a code, when there is no error to read it from. */
export function messageForCode(code: string): string {
  return MESSAGES[code] ?? "Something went wrong. Try again.";
}

export function messageForError(error: unknown): string {
  if (error instanceof ApiError) {
    // The server knows what the file actually is, so for a file problem
    // its message is the one that says what to do about it.
    if (error.code === "FILE_NOT_PDF" && error.message.length > 0) {
      return error.message;
    }
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
