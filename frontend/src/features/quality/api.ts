import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  apiRequest,
  type ApiError,
  type QualityPageResponse,
  type QualityReportResponse,
} from "../../api/client";

/**
 * The quality endpoints are addressed by upload id. Analysis is queued by
 * the worker, and acknowledgement is advisory: it is recorded but never
 * required to place an order.
 */
export type QualityReportStatus = "PENDING" | "RUNNING" | "DONE" | "FAILED";

export type QualityPageFlag = QualityPageResponse;

export type QualityReport = QualityReportResponse;

const reportPath = (uploadId: string) => `/uploads/${uploadId}/quality`;

export function getQualityReport(uploadId: string): Promise<QualityReport> {
  return apiRequest(reportPath(uploadId));
}

/** Triggering is deliberately separate: analysis runs in the worker. */
export function requestQualityReport(uploadId: string): Promise<QualityReport> {
  return apiRequest(reportPath(uploadId), { method: "POST" });
}

/**
 * The customer has seen the warnings and is going ahead. It is recorded
 * on the report and on the order, and it never blocks the order.
 */
export function acknowledgeQualityReport(
  uploadId: string,
): Promise<QualityReport> {
  return apiRequest(`${reportPath(uploadId)}/acknowledge`, {
    method: "POST",
  });
}

export function useQualityReport(uploadId: string | undefined, enabled = true) {
  return useQuery<QualityReport, ApiError>({
    queryKey: ["quality-report", uploadId],
    queryFn: () => getQualityReport(uploadId as string),
    enabled: uploadId !== undefined && enabled,
    retry: false,
    // The report is produced by the worker, so the page waits for it
    // while it is running and stops asking once it is done.
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "PENDING" || status === "RUNNING" ? 2000 : false;
    },
  });
}

export function useRequestQualityReport(uploadId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation<QualityReport, ApiError>({
    mutationFn: () => requestQualityReport(uploadId as string),
    onSuccess: (report) => {
      queryClient.setQueryData(["quality-report", uploadId], report);
    },
  });
}

export function useAcknowledgeQualityReport(uploadId: string | undefined) {
  const queryClient = useQueryClient();
  return useMutation<QualityReport, ApiError>({
    mutationFn: () => acknowledgeQualityReport(uploadId as string),
    onSuccess: (report) => {
      queryClient.setQueryData(["quality-report", uploadId], report);
    },
  });
}
