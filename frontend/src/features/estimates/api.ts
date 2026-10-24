import { useQuery } from "@tanstack/react-query";

import { apiRequest, type WaitEstimateResponse } from "../../api/client";

export function getWaitEstimate(shopId: string): Promise<WaitEstimateResponse> {
  return apiRequest(`/shops/${shopId}/wait-estimate`);
}

export function useWaitEstimate(shopId: string | undefined) {
  return useQuery({
    queryKey: ["shops", "wait-estimate", shopId],
    queryFn: () => getWaitEstimate(shopId as string),
    enabled: shopId !== undefined,
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
    retry: false,
  });
}
