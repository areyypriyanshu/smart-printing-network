import { ApiError } from "../../api/client";
import { Alert, Button, sectionTitleClassName } from "../../components/ui";
import { messageForError } from "../../lib/errors";
import type { QualityReport } from "./api";

type QualityReportCardProps = {
  report?: QualityReport;
  isLoading?: boolean;
  isRequesting?: boolean;
  isAcknowledging?: boolean;
  error?: unknown;
  acknowledgeError?: unknown;
  onRequest?: () => void;
  onAcknowledge?: () => void;
};

/** What the customer is told about each flag, in plain words. */
const FLAG_MESSAGES: Record<string, string> = {
  LOW_RESOLUTION: "the picture is printed at a low resolution",
  VERY_LOW_RESOLUTION: "the picture has too few pixels and will look blocky",
  BLURRY: "the picture is blurry",
};

function flagMessage(flags: string[]): string {
  const known = flags
    .map((flag) => FLAG_MESSAGES[flag])
    .filter((message): message is string => message !== undefined);
  if (known.length === 0) return "this page may not print well";
  const sentences = known.map((message) => `${message}.`);
  return sentences.join(" ");
}

/**
 * Advisory quality feedback. A report must never prevent checkout.
 */
export function QualityReportCard({
  report,
  isLoading = false,
  isRequesting = false,
  isAcknowledging = false,
  error,
  acknowledgeError,
  onRequest,
  onAcknowledge,
}: QualityReportCardProps) {
  if (isLoading) {
    return (
      <p role="status" className="text-sm text-steel">
        Checking file quality…
      </p>
    );
  }

  if (error !== undefined && report === undefined) {
    // A report that has not been asked for yet is not a failure: the
    // check simply has not run. The customer can start it.
    const notAskedFor = error instanceof ApiError && error.status === 404;
    return (
      <section
        aria-label="File quality"
        className="flex flex-col gap-3 rounded-xl border border-hairline bg-canvas p-5"
      >
        <h2 className={sectionTitleClassName()}>File quality</h2>
        <p className="text-sm text-steel">
          {notAskedFor
            ? "We can check the pages of this file before you order. You can also order without checking."
            : "The quality check is not available right now. You can still continue with your order."}
        </p>
        {onRequest !== undefined && (
          <div>
            <Button
              variant="secondary"
              onClick={onRequest}
              pending={isRequesting}
              pendingLabel="Starting check…"
            >
              Check file quality
            </Button>
          </div>
        )}
      </section>
    );
  }

  if (report === undefined) return null;

  if (report.status === "PENDING" || report.status === "RUNNING") {
    return (
      <section
        aria-label="File quality"
        className="flex flex-col gap-2 rounded-xl border border-hairline bg-canvas p-5"
      >
        <h2 className={sectionTitleClassName()}>File quality</h2>
        <p role="status" className="text-sm text-steel">
          Your file is being checked. You can continue while it runs.
        </p>
      </section>
    );
  }

  if (report.status === "FAILED") {
    return (
      <section
        aria-label="File quality"
        className="flex flex-col gap-2 rounded-xl border border-hairline bg-canvas p-5"
      >
        <h2 className={sectionTitleClassName()}>File quality</h2>
        <p className="text-sm text-steel">
          We could not complete the quality check. This does not block your
          order.
        </p>
      </section>
    );
  }

  const flagged = report.pages.filter((page) => page.flags.length > 0);
  if (flagged.length === 0) {
    return (
      <section
        aria-label="File quality"
        className="flex flex-col gap-2 rounded-xl border border-hairline bg-canvas p-5"
      >
        <h2 className={sectionTitleClassName()}>File quality</h2>
        <p className="text-sm text-steel">No quality warnings were found.</p>
      </section>
    );
  }

  return (
    <section
      aria-label="File quality"
      className="flex flex-col gap-3 rounded-xl border border-warning bg-cream-deeper p-5"
    >
      <div>
        <h2 className={sectionTitleClassName()}>Check your file quality</h2>
        <p className="mt-1 text-sm text-steel">
          Some pages may print blurry or pixelated. These warnings are advisory;
          you can still order.
        </p>
      </div>
      <ul
        className="flex flex-col gap-2 text-sm text-ink"
        aria-label="Quality warnings"
      >
        {flagged.map((page) => (
          <li key={page.page_number}>
            <strong>Page {page.page_number}:</strong> {flagMessage(page.flags)}
          </li>
        ))}
      </ul>
      {acknowledgeError !== undefined && (
        <Alert>{messageForError(acknowledgeError)}</Alert>
      )}
      {report.acknowledged ? (
        <p role="status" className="text-sm text-steel">
          Warnings acknowledged. You can proceed.
        </p>
      ) : onAcknowledge !== undefined ? (
        <div>
          <Button
            onClick={onAcknowledge}
            pending={isAcknowledging}
            pendingLabel="Saving…"
          >
            Acknowledge and continue
          </Button>
        </div>
      ) : null}
    </section>
  );
}
