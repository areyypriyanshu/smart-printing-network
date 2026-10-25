import { apiRequest } from "./client";
import type { components } from "./schema";

export type OrderResponse = components["schemas"]["OrderResponse"];
export type OrderCreateResponse = components["schemas"]["OrderCreateResponse"];
export type OrderDetailResponse = components["schemas"]["OrderDetailResponse"];
export type OrderEventResponse = components["schemas"]["OrderEventResponse"];
export type OrderListResponse = components["schemas"]["OrderListResponse"];

export type OrderCreateBody = {
  upload_id: string;
  shop_id: string;
  paper_size: "A4" | "A3";
  color: boolean;
  duplex: boolean;
  copies: number;
  expected_price_paise?: number;
  quality_acknowledged?: boolean;
};

export const ORDER_STATUSES = [
  "PENDING_PAYMENT",
  "PAID",
  "RESERVED",
  "ACCEPTED",
  "PRINTING",
  "READY",
  "COLLECTED",
  "REJECTED",
  "CANCELLED",
  "EXPIRED",
] as const;

export type OrderStatus = (typeof ORDER_STATUSES)[number];

export const TERMINAL_STATUSES: readonly OrderStatus[] = [
  "COLLECTED",
  "REJECTED",
  "CANCELLED",
  "EXPIRED",
];

export const STATUS_LABELS: Record<OrderStatus, string> = {
  PENDING_PAYMENT: "Waiting for payment",
  PAID: "Paid, waiting for the shop",
  RESERVED: "Reserved, waiting for the shop",
  ACCEPTED: "Accepted by the shop",
  PRINTING: "Printing",
  READY: "Ready for pickup",
  COLLECTED: "Collected",
  REJECTED: "Rejected",
  CANCELLED: "Cancelled",
  EXPIRED: "Expired",
};

export function isTerminalStatus(status: string): boolean {
  return (TERMINAL_STATUSES as readonly string[]).includes(status);
}

export function statusLabel(status: string): string {
  return STATUS_LABELS[status as OrderStatus] ?? status;
}

/**
 * The label for an order, in words that fit how it is paid for.
 *
 * A cash order is not "paid" until it is collected, so it never says so.
 * The customer must never be told to pay online for an order they are
 * going to pay for in cash at the counter.
 */
export function orderStatusLabel(order: {
  status: string;
  payment_method: string;
}): string {
  if (order.payment_method === "at_store") {
    if (order.status === "RESERVED") return "Reserved, waiting for the shop";
    if (order.status === "READY") return "Ready for pickup, pay at the counter";
    if (order.status === "COLLECTED") return "Collected and paid in cash";
  }
  return statusLabel(order.status);
}

export function createOrder(
  body: OrderCreateBody,
  idempotencyKey: string,
): Promise<OrderCreateResponse> {
  return apiRequest("/orders", {
    method: "POST",
    body,
    headers: { "Idempotency-Key": idempotencyKey },
  });
}

export function getOrder(orderId: string): Promise<OrderDetailResponse> {
  return apiRequest(`/orders/${orderId}`);
}

export type ReorderResponse = components["schemas"]["ReorderResponse"];

/**
 * Book the same job again. The file is copied, so the new order has its
 * own file and its own retention window.
 */
export function reorderOrder(orderId: string): Promise<ReorderResponse> {
  return apiRequest(`/orders/${orderId}/reorder`, { method: "POST" });
}

export function listOrders(cursor?: number): Promise<OrderListResponse> {
  const query = cursor === undefined ? "" : `?cursor=${cursor}`;
  return apiRequest(`/orders${query}`);
}
