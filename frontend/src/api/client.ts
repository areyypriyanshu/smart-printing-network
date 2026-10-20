import type { components } from "./schema";

export type User = components["schemas"]["UserResponse"];
export type AccessTokenResponse = components["schemas"]["AccessTokenResponse"];
export type LoginRequest = components["schemas"]["LoginRequest"];
export type RegisterRequest = components["schemas"]["RegisterRequest"];
export type RegisterVendorRequest =
  components["schemas"]["RegisterVendorRequest"];
export type VendorRegistrationResponse =
  components["schemas"]["VendorRegistrationResponse"];
export type UserResponse = components["schemas"]["UserResponse"];
export type Role = User["role"];
export type RateItem = components["schemas"]["RateItem"];
export type RatesReplaceRequest = components["schemas"]["RatesReplaceRequest"];
export type ShopListResponse = components["schemas"]["ShopListResponse"];
export type ShopResponse = components["schemas"]["ShopResponse"];
export type VendorShopResponse = components["schemas"]["VendorShopResponse"];
export type VendorShopUpdate = components["schemas"]["VendorShopUpdate"];
export type UploadResponse = components["schemas"]["UploadResponse"];
export type QuoteRequest = components["schemas"]["QuoteRequest"];
export type QuoteResponse = components["schemas"]["QuoteResponse"];
export type VerifyEmailRequest = components["schemas"]["VerifyEmailRequest"];
export type ChangeEmailRequest = components["schemas"]["ChangeEmailRequest"];
export type VerificationSentResponse =
  components["schemas"]["VerificationSentResponse"];
export type OAuthProvidersResponse = {
  providers: string[];
};
export type OAuthStartResponse = { url: string };

export type ApiErrorBody = {
  error?: {
    code?: string;
    message?: string;
    details?: unknown;
    request_id?: string;
  };
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;
  readonly requestId: string | null;

  constructor(
    status: number,
    code: string,
    message: string,
    details: unknown,
    requestId: string | null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

const API_BASE = "/api/v1";

let accessToken: string | null = null;
let onSessionExpired: (() => void) | null = null;

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

export function currentAccessToken(): string | null {
  return accessToken;
}

export function setSessionExpiredHandler(handler: (() => void) | null): void {
  onSessionExpired = handler;
}

async function parseError(response: Response): Promise<ApiError> {
  let body: ApiErrorBody | null;
  try {
    body = (await response.json()) as ApiErrorBody;
  } catch {
    body = null;
  }
  const code = body?.error?.code ?? "UNKNOWN_ERROR";
  const message =
    body?.error?.message ?? `Request failed with status ${response.status}`;
  return new ApiError(
    response.status,
    code,
    message,
    body?.error?.details ?? {},
    body?.error?.request_id ?? null,
  );
}

export type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  headers?: Record<string, string>;
  retryOnUnauthorized?: boolean;
};

async function send(path: string, options: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { ...options.headers };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (accessToken !== null) headers.Authorization = `Bearer ${accessToken}`;
  return fetch(`${API_BASE}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
}

let refreshInFlight: Promise<string | null> | null = null;

export async function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight !== null) return refreshInFlight;
  const attempt = (async () => {
    try {
      const response = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
      });
      if (!response.ok) return null;
      const data = (await response.json()) as AccessTokenResponse;
      accessToken = data.access_token;
      return data.access_token;
    } catch {
      return null;
    }
  })();
  refreshInFlight = attempt;
  try {
    return await attempt;
  } finally {
    refreshInFlight = null;
  }
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  let response = await send(path, options);

  if (response.status === 401 && options.retryOnUnauthorized !== false) {
    const token = await refreshAccessToken();
    if (token !== null) {
      response = await send(path, options);
    } else {
      accessToken = null;
      onSessionExpired?.();
    }
  }

  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
