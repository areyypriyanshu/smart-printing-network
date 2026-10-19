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

export function useShops() {
  return useQuery({
    queryKey: ["shops", { limit: 100 }],
    queryFn: listShops,
    retry: false,
  });
}
