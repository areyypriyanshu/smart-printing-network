import {
  apiRequest,
  type AccessTokenResponse,
  type ChangeEmailRequest,
  type LoginRequest,
  type RegisterRequest,
  type RegisterVendorRequest,
  type User,
  type VendorRegistrationResponse,
  type VerificationSentResponse,
} from "../../api/client";

export function loginRequest(body: LoginRequest): Promise<AccessTokenResponse> {
  return apiRequest("/auth/login", {
    method: "POST",
    body,
    retryOnUnauthorized: false,
  });
}

export function registerRequest(body: RegisterRequest): Promise<User> {
  return apiRequest("/auth/register", {
    method: "POST",
    body,
    retryOnUnauthorized: false,
  });
}

export function registerVendorRequest(
  body: RegisterVendorRequest,
): Promise<VendorRegistrationResponse> {
  return apiRequest("/auth/register-vendor", {
    method: "POST",
    body,
    retryOnUnauthorized: false,
  });
}

export function logoutRequest(): Promise<void> {
  return apiRequest("/auth/logout", {
    method: "POST",
    retryOnUnauthorized: false,
  });
}

export function meRequest(): Promise<User> {
  return apiRequest("/me", { retryOnUnauthorized: false });
}

/** Prove the address from the token in the link that was sent to it. */
export function verifyEmailRequest(token: string): Promise<User> {
  return apiRequest("/auth/verify-email", {
    method: "POST",
    body: { token },
    retryOnUnauthorized: false,
  });
}

/** Ask for the link again, to the address the account holds. */
export function resendVerificationRequest(): Promise<VerificationSentResponse> {
  return apiRequest("/auth/resend-verification", { method: "POST" });
}

/** Put a different address on the account. */
export function changeEmailRequest(body: ChangeEmailRequest): Promise<User> {
  return apiRequest("/auth/change-email", { method: "POST", body });
}
