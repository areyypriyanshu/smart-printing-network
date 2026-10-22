import { useQuery } from "@tanstack/react-query";

import { apiRequest, type ShopSearchResponse } from "../../api/client";

export type { ShopSearchItem, ShopSearchResponse } from "../../api/client";

export type ShopSearchQuery = {
  latitude?: number;
  longitude?: number;
  address?: string;
  radius_m?: number;
  sort?: "distance" | "price";
  upload_id?: string;
  paper_size?: "A4" | "A3";
  color?: boolean;
  duplex?: boolean;
  copies?: number;
  limit?: number;
};

/**
 * The shops around the customer, with what they would charge.
 *
 * The prices come from the server, from the same function the order
 * flow uses, so what is shown here is what would be charged.
 */
export function searchShops(
  query: ShopSearchQuery,
): Promise<ShopSearchResponse> {
  const params = new URLSearchParams();
  if (query.latitude !== undefined)
    params.set("latitude", String(query.latitude));
  if (query.longitude !== undefined)
    params.set("longitude", String(query.longitude));
  if (query.address !== undefined) params.set("address", query.address);
  if (query.radius_m !== undefined)
    params.set("radius_m", String(query.radius_m));
  if (query.sort !== undefined) params.set("sort", query.sort);
  if (query.upload_id !== undefined) params.set("upload_id", query.upload_id);
  if (query.paper_size !== undefined)
    params.set("paper_size", query.paper_size);
  if (query.color !== undefined) params.set("color", String(query.color));
  if (query.duplex !== undefined) params.set("duplex", String(query.duplex));
  if (query.copies !== undefined) params.set("copies", String(query.copies));
  if (query.limit !== undefined) params.set("limit", String(query.limit));
  return apiRequest(`/shops/search?${params.toString()}`);
}

export function useShopSearch(query: ShopSearchQuery | null) {
  return useQuery({
    queryKey: ["shops", "search", query],
    queryFn: () => searchShops(query as ShopSearchQuery),
    enabled: query !== null,
    retry: false,
  });
}
