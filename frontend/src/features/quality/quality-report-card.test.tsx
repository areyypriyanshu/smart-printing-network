import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../../api/client";
import { renderWithProviders } from "../../test/render";
import type { QualityReport } from "./api";
import { QualityReportCard } from "./quality-report-card";

const flaggedReport: QualityReport = {
  id: "report-1",
  upload_id: "upload-1",
  status: "DONE",
  summary: { page_count: 3, flagged_pages: 1, flagged: true },
  error: null,
  acknowledged: false,
  algorithm_version: "1",
  created_at: "2026-01-01T00:00:00Z",
  started_at: null,
  completed_at: null,
  pages: [
    {
      page_number: 2,
      flags: ["BLURRY"],
      min_effective_dpi: 300,
      blur_score: 12,
    },
    {
      page_number: 3,
      flags: [],
      min_effective_dpi: 300,
      blur_score: 900,
    },
  ],
};

describe("QualityReportCard", () => {
  it("shows page warnings and lets the customer acknowledge them", async () => {
    const user = userEvent.setup();
    const onAcknowledge = vi.fn();
    renderWithProviders(
      <QualityReportCard
        report={flaggedReport}
        onAcknowledge={onAcknowledge}
      />,
    );

    expect(
      screen.getByRole("heading", { name: /check your file quality/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/page 2/i)).toBeInTheDocument();
    expect(screen.getByText(/the picture is blurry/i)).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: /acknowledge and continue/i }),
    );
    expect(onAcknowledge).toHaveBeenCalledOnce();
  });

  it("keeps checkout available when the quality service is unavailable", () => {
    renderWithProviders(
      <QualityReportCard error={new Error("not ready")} onRequest={vi.fn()} />,
    );

    expect(screen.getByText(/can still continue/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /check file quality/i }),
    ).toBeInTheDocument();
  });

  it("does not report a failure before an acknowledgement was attempted", () => {
    // TanStack Query starts a mutation with error: null, not undefined.
    renderWithProviders(
      <QualityReportCard
        report={flaggedReport}
        acknowledgeError={null}
        onAcknowledge={vi.fn()}
      />,
    );

    expect(screen.queryByText(/something went wrong/i)).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /acknowledge and continue/i }),
    ).toBeInTheDocument();
  });

  it("renders nothing when there is neither a report nor an error", () => {
    const { container } = renderWithProviders(
      <QualityReportCard error={null} />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("offers the check when the file has not been checked yet", () => {
    renderWithProviders(
      <QualityReportCard
        error={
          new ApiError(404, "NOT_FOUND", "Quality report not found", {}, null)
        }
        onRequest={vi.fn()}
      />,
    );

    expect(
      screen.getByText(/can check the pages of this file/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /check file quality/i }),
    ).toBeInTheDocument();
  });

  it("shows a clean result without an acknowledgement action", () => {
    renderWithProviders(
      <QualityReportCard
        report={{ ...flaggedReport, pages: [], summary: { flagged: false } }}
      />,
    );

    expect(screen.getByText(/no quality warnings/i)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("says the warnings were already acknowledged", () => {
    renderWithProviders(
      <QualityReportCard
        report={{ ...flaggedReport, acknowledged: true }}
        onAcknowledge={vi.fn()}
      />,
    );

    expect(screen.getByText(/warnings acknowledged/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /acknowledge and continue/i }),
    ).not.toBeInTheDocument();
  });

  it("says a failed check does not block the order", () => {
    renderWithProviders(
      <QualityReportCard
        report={{ ...flaggedReport, status: "FAILED", error: "boom" }}
      />,
    );

    expect(screen.getByText(/does not block your order/i)).toBeInTheDocument();
  });
});
