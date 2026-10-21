import { useQueries, useQuery } from "@tanstack/react-query";

import {
  ApiError,
  apiRequest,
  currentToken,
  type ApiErrorBody,
  type QuoteRequest,
  type QuoteResponse,
  type UploadResponse,
} from "../../api/client";
import type { Shop } from "../shops/api";
import type { OptionsFormValues } from "./schemas";

export function getUpload(uploadId: string): Promise<UploadResponse> {
  return apiRequest(`/uploads/${uploadId}`);
}

export function createQuote(body: QuoteRequest): Promise<QuoteResponse> {
  return apiRequest("/quotes", { method: "POST", body });
}

export function useUpload(uploadId: string | null) {
  return useQuery({
    queryKey: ["uploads", uploadId],
    queryFn: () => getUpload(uploadId as string),
    enabled: uploadId !== null,
    retry: false,
  });
}

type UploadHandle = {
  promise: Promise<UploadResponse>;
  abort: () => void;
};

function xhrError(xhr: XMLHttpRequest): ApiError {
  let body: ApiErrorBody | null;
  try {
    body = JSON.parse(xhr.responseText) as ApiErrorBody;
  } catch {
    body = null;
  }
  const code = body?.error?.code ?? "UNKNOWN_ERROR";
  const message =
    body?.error?.message ?? `Request failed with status ${xhr.status}`;
  return new ApiError(
    xhr.status,
    code,
    message,
    body?.error?.details ?? {},
    body?.error?.request_id ?? null,
  );
}

export function uploadPdf(
  file: File,
  onProgress: (fraction: number) => void,
): UploadHandle {
  const xhr = new XMLHttpRequest();
  let retried = false;

  const attempt = async () => {
    const form = new FormData();
    form.append("file", file, file.name);
    const token = await currentToken();
    xhr.open("POST", "/api/v1/uploads");
    if (token !== null)
      xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.send(form);
  };

  const promise = new Promise<UploadResponse>((resolve, reject) => {
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) {
        onProgress(event.loaded / event.total);
      }
    };
    xhr.onload = () => {
      void (async () => {
        if (xhr.status === 401 && !retried) {
          // The token may have expired between the browser asking for
          // it and the server checking it. It is asked for again, and
          // the upload is tried once more.
          retried = true;
          if ((await currentToken()) !== null) {
            void attempt();
            return;
          }
        }
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(JSON.parse(xhr.responseText) as UploadResponse);
          return;
        }
        reject(xhrError(xhr));
      })();
    };
    xhr.onerror = () =>
      reject(
        new ApiError(
          0,
          "NETWORK_ERROR",
          "The upload could not reach the server.",
          {},
          null,
        ),
      );
    xhr.onabort = () =>
      reject(new ApiError(0, "ABORTED", "Upload cancelled.", {}, null));
    attempt();
  });

  return { promise, abort: () => xhr.abort() };
}

export type QuoteState =
  | { status: "pending" }
  | { status: "ok"; quote: QuoteResponse }
  | { status: "unavailable"; code: string }
  | { status: "error"; error: unknown };

export type ShopQuote = {
  shop: Shop;
  state: QuoteState;
};

const UNAVAILABLE_CODES = new Set(["RATE_NOT_SET", "SHOP_UNAVAILABLE"]);

export function useShopQuotes(
  uploadId: string | null,
  shops: Shop[],
  options: OptionsFormValues | null,
): ShopQuote[] {
  const enabled = uploadId !== null && options !== null;
  const results = useQueries({
    queries: (enabled ? shops : []).map((shop) => ({
      queryKey: [
        "quotes",
        uploadId,
        shop.id,
        options?.paper_size,
        options?.color,
        options?.duplex,
        options?.copies,
      ],
      queryFn: () =>
        createQuote({
          upload_id: uploadId as string,
          shop_id: shop.id,
          paper_size: options?.paper_size ?? "A4",
          color: options?.color ?? false,
          duplex: options?.duplex ?? false,
          copies: options?.copies ?? 1,
        }),
      retry: false,
    })),
  });

  return shops.map((shop, index) => {
    const result = results[index];
    if (result === undefined || result.isPending) {
      return { shop, state: { status: "pending" } };
    }
    if (result.isError) {
      const error = result.error;
      if (error instanceof ApiError && UNAVAILABLE_CODES.has(error.code)) {
        return { shop, state: { status: "unavailable", code: error.code } };
      }
      return { shop, state: { status: "error", error } };
    }
    return { shop, state: { status: "ok", quote: result.data } };
  });
}
