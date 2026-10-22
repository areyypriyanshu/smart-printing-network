import { useQueries, useQuery } from "@tanstack/react-query";

import {
  ApiError,
  apiRequest,
  type QuoteRequest,
  type QuoteResponse,
} from "../../api/client";
import { getUpload } from "../../api/upload";
import type { Shop } from "../shops/api";
import type { OptionsFormValues } from "./schemas";

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
