import { http, HttpResponse } from "msw";

import type { User } from "../../api/client";

export const customerUser: User = {
  id: "8fd2dc7c-2f2e-4d70-9f5e-bc1a0c8a1a11",
  email: "customer@example.com",
  full_name: "Customer One",
  role: "customer",
  created_at: "2026-01-01T00:00:00Z",
};

export const vendorUser: User = {
  id: "5d3f7d6e-6d1c-4f5e-9a2b-8f9a3f4c2b22",
  email: "vendor@example.com",
  full_name: "Vendor One",
  role: "vendor",
  created_at: "2026-01-01T00:00:00Z",
};

export const adminUser: User = {
  id: "9a1c4e77-2b3d-4c8a-9f1e-7d6c5b4a3e2f",
  email: "admin@example.com",
  full_name: "Owner",
  role: "admin",
  created_at: "2026-01-01T00:00:00Z",
};

export const errorResponse = (
  status: number,
  code: string,
  message: string,
  requestId = "req-test",
) =>
  HttpResponse.json(
    { error: { code, message, details: {}, request_id: requestId } },
    { status },
  );

export const handlers = [
  http.get("/api/v1/me", () =>
    errorResponse(401, "UNAUTHENTICATED", "Authentication required"),
  ),
];
