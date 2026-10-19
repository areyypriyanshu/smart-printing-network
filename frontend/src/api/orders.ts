import { apiRequest } from "./client";
import type { components } from "./schema";

export type OrderResponse = components["schemas"]["OrderResponse"];
export type OrderCreateResponse = components["schemas"]["OrderCreateResponse"];
export type OrderDetailResponse = components["schemas"]["OrderDetailResponse"];
export type OrderEventResponse = components["schemas"]["OrderEventResponse"];
export type OrderListResponse = components["schemas"]["OrderListResponse"];
export type PaymentCheckoutResponse =
  components["schemas"]["PaymentCheckoutResponse"];

export type OrderCreateBody = {
  upload_id: string;
  shop_id: string;
  paper_size: "A4" | "A3";
  color: boolean;
  duplex: boolean;
  copies: number;
  expected_price_paise?: number;
};

export const ORDER_STATUSES = [
  "PENDING_PAYMENT",
  "PAID",
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

export function listOrders(cursor?: number): Promise<OrderListResponse> {
  const query = cursor === undefined ? "" : `?cursor=${cursor}`;
  return apiRequest(`/orders${query}`);
}

export function simulatePayment(orderId: string): Promise<{ status: string }> {
  return apiRequest("/testing/simulate-payment", {
    method: "POST",
    body: { order_id: orderId },
  });
}
