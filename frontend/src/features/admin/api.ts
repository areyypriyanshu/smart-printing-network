import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
} from "@tanstack/react-query";

import { apiRequest } from "../../api/client";
import type { components } from "../../api/schema";

export type AdminShop = components["schemas"]["AdminShopResponse"];
export type AdminShopList = components["schemas"]["AdminShopListResponse"];
export type AdminAction = components["schemas"]["AdminActionResponse"];
export type AdminActionList = components["schemas"]["AdminActionListResponse"];

export type ShopStatus = "pending" | "verified" | "all";

export function getAdminShops(status: ShopStatus): Promise<AdminShopList> {
  return apiRequest(`/admin/shops?status=${status}&limit=200`);
}

export function useAdminShops(status: ShopStatus) {
  return useQuery({
    queryKey: ["admin", "shops", status],
    queryFn: () => getAdminShops(status),
    retry: false,
  });
}

export function approveShop(shopId: string): Promise<AdminShop> {
  return apiRequest(`/admin/shops/${shopId}/approve`, {
    method: "POST",
    body: {},
  });
}

export function suspendShop(
  shopId: string,
  reason: string,
): Promise<AdminShop> {
  return apiRequest(`/admin/shops/${shopId}/suspend`, {
    method: "POST",
    body: { reason },
  });
}

type ShopAction =
  | { action: "approve"; shopId: string }
  | { action: "suspend"; shopId: string; reason: string };

/**
 * Approving or suspending a shop changes what the shop list looks like
 * and what the log says, so both are invalidated when it succeeds.
 */
export function useShopAction(): UseMutationResult<
  AdminShop,
  unknown,
  ShopAction
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ action, shopId, ...rest }) =>
      action === "approve"
        ? approveShop(shopId)
        : suspendShop(shopId, (rest as { reason: string }).reason),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["admin"] });
    },
  });
}

export function getAdminActions(): Promise<AdminActionList> {
  return apiRequest("/admin/actions?limit=100");
}

export function useAdminActions() {
  return useQuery({
    queryKey: ["admin", "actions"],
    queryFn: getAdminActions,
    retry: false,
  });
}
