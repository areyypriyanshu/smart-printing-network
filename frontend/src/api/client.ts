import type { components } from "./schema";

export type User = components["schemas"]["UserResponse"];
export type OnboardingRequest = components["schemas"]["OnboardingRequest"];
export type UserResponse = components["schemas"]["UserResponse"];
export type Role = User["role"];
export type RateItem = components["schemas"]["RateItem"];
export type RateToSet = components["schemas"]["RateToSet"];
export type RatesReplaceRequest = components["schemas"]["RatesReplaceRequest"];
export type ShopListResponse = components["schemas"]["ShopListResponse"];
export type ShopResponse = components["schemas"]["ShopResponse"];
export type ShopSearchItem = components["schemas"]["ShopSearchItem"];
export type ShopSearchResponse = components["schemas"]["ShopSearchResponse"];
export type WaitEstimateResponse =
  components["schemas"]["WaitEstimateResponse"];
export type VendorShopResponse = components["schemas"]["VendorShopResponse"];
export type VendorShopUpdate = components["schemas"]["VendorShopUpdate"];
export type UploadResponse = components["schemas"]["UploadResponse"];
export type QuoteRequest = components["schemas"]["QuoteRequest"];
export type QuoteResponse = components["schemas"]["QuoteResponse"];
export type QualityReportResponse =
  components["schemas"]["QualityReportResponse"];
export type QualityPageResponse = components["schemas"]["QualityPageResponse"];

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

/**
 * Where the session token comes from.
 *
 * The token is not held here. It is held by the identity provider,
 * which refreshes it on its own, and this asks for a fresh one when a
 * request needs it. A token that is cached here would be one that has
 * expired, because it lives about a minute.
 */
export type TokenSource = () => Promise<string | null>;

let tokenSource: TokenSource | null = null;

export function setTokenSource(source: TokenSource | null): void {
  tokenSource = source;
}

export async function currentToken(): Promise<string | null> {
  if (tokenSource === null) return null;
  return tokenSource();
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
};

async function send(path: string, options: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { ...options.headers };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  const token = await currentToken();
  if (token !== null) headers.Authorization = `Bearer ${token}`;
  return fetch(`${API_BASE}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const response = await send(path, options);

  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
