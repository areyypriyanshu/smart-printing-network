import { useQuery } from "@tanstack/react-query";

import {
  apiRequest,
  type ShopListResponse,
  type ShopResponse,
} from "../../api/client";

export type Shop = ShopResponse;

export function listShops(): Promise<ShopListResponse> {
  return apiRequest("/shops?limit=100");
}

export function getShop(shopId: string): Promise<ShopResponse> {
  return apiRequest(`/shops/${shopId}`);
}

export function useShop(shopId: string | undefined) {
  return useQuery({
    queryKey: ["shops", "one", shopId],
    queryFn: () => getShop(shopId as string),
    enabled: shopId !== undefined,
    retry: false,
  });
}

export type NearbyQuery = {
  latitude: number;
  longitude: number;
  radius_m?: number;
  limit?: number;
};

/**
 * The shops around a point, nearest first. The distance on each shop is
 * in metres.
 */
export function listNearbyShops(query: NearbyQuery): Promise<ShopListResponse> {
  const params = new URLSearchParams({
    latitude: String(query.latitude),
    longitude: String(query.longitude),
    radius_m: String(query.radius_m ?? 5000),
    limit: String(query.limit ?? 50),
  });
  return apiRequest(`/shops/nearby?${params.toString()}`);
}

export function useNearbyShops(query: NearbyQuery | null) {
  return useQuery({
    queryKey: [
      "shops",
      "nearby",
      query?.latitude ?? null,
      query?.longitude ?? null,
      query?.radius_m ?? null,
    ],
    queryFn: () => listNearbyShops(query as NearbyQuery),
    enabled: query !== null,
    retry: false,
  });
}

export function useShops() {
  return useQuery({
    queryKey: ["shops", { limit: 100 }],
    queryFn: listShops,
    retry: false,
  });
}
