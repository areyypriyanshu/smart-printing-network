import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  apiRequest,
  type VendorShopResponse,
  type VendorShopUpdate,
} from "../../api/client";

export function getVendorShop(): Promise<VendorShopResponse> {
  return apiRequest("/vendor/shop");
}

export function useVendorShop() {
  return useQuery({
    queryKey: ["vendor", "shop"],
    queryFn: getVendorShop,
    retry: false,
  });
}

export function patchVendorShop(
  body: VendorShopUpdate,
): Promise<VendorShopResponse> {
  return apiRequest("/vendor/shop", { method: "PATCH", body });
}

export function useUpdateVendorShop() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: patchVendorShop,
    onSuccess: (shop) => {
      queryClient.setQueryData(["vendor", "shop"], shop);
      void queryClient.invalidateQueries({ queryKey: ["shops"] });
    },
  });
}
