import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
} from "@tanstack/react-query";

import { apiRequest } from "../../api/client";
import type { components } from "../../api/schema";

export type VendorOrder = components["schemas"]["VendorOrderResponse"];
export type VendorQueueResponse = components["schemas"]["VendorQueueResponse"];
export type VendorOrderDetail =
  components["schemas"]["VendorOrderDetailResponse"];

export const QUEUE_POLL_INTERVAL_MS = 5000;

export function getQueue(): Promise<VendorQueueResponse> {
  return apiRequest("/vendor/queue");
}

export function useQueue() {
  return useQuery({
    queryKey: ["vendor", "queue"],
    queryFn: getQueue,
    // The board is a live view of the counter. It polls while the tab is
    // visible and stops in the background so a forgotten tab does not keep
    // hammering the API.
    refetchInterval: QUEUE_POLL_INTERVAL_MS,
    refetchIntervalInBackground: false,
    retry: false,
  });
}

type Action = "accept" | "reject" | "start" | "ready" | "cancel" | "collect";

export function vendorAction(
  orderId: string,
  action: Action,
  body?: { reason?: string; code?: string },
): Promise<VendorOrder> {
  return apiRequest(`/vendor/orders/${orderId}/${action}`, {
    method: "POST",
    body: body ?? {},
  });
}

export function useVendorAction(): UseMutationResult<
  VendorOrder,
  unknown,
  { orderId: string; action: Action; body?: { reason?: string; code?: string } }
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ orderId, action, body }) =>
      vendorAction(orderId, action, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["vendor", "queue"] });
    },
  });
}

export function getOrderFile(orderId: string): Promise<{ url: string }> {
  return apiRequest(`/vendor/orders/${orderId}/file`);
}
