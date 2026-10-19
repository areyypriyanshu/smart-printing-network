import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  apiRequest,
  type RateItem,
  type RatesReplaceRequest,
} from "../../api/client";

export function getVendorRates(): Promise<RateItem[]> {
  return apiRequest("/vendor/rates");
}

export function putVendorRates(body: RatesReplaceRequest): Promise<RateItem[]> {
  return apiRequest("/vendor/rates", { method: "PUT", body });
}

export function useVendorRates() {
  return useQuery({
    queryKey: ["vendor", "rates"],
    queryFn: getVendorRates,
    retry: false,
  });
}

export function useReplaceVendorRates() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: putVendorRates,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["vendor", "rates"] });
      void queryClient.invalidateQueries({ queryKey: ["shops"] });
    },
  });
}
