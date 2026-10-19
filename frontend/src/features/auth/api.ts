import {
  apiRequest,
  type AccessTokenResponse,
  type LoginRequest,
  type RegisterRequest,
  type RegisterVendorRequest,
  type User,
  type VendorRegistrationResponse,
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
