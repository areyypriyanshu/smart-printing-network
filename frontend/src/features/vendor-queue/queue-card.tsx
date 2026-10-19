import { useState } from "react";

import { Alert, Button } from "../../components/ui";
import { messageForError } from "../../lib/errors";
import { relativeTime, minutesSince } from "../../lib/dates";
import { formatPaise } from "../../lib/money";
import { getOrderFile, type VendorOrder } from "./api";

const WARNING_WINDOW_MINUTES = 5;

type QueueCardProps = {
  order: VendorOrder;
  now: Date;
  acceptTimeoutMinutes: number;
  pending: boolean;
  onAccept: () => void;
  onReject: () => void;
  onStart: () => void;
  onReady: () => void;
  onCancel: () => void;
  onCollect: () => void;
};

export function QueueCard({
  order,
  now,
  acceptTimeoutMinutes,
  pending,
  onAccept,
  onReject,
  onStart,
  onReady,
  onCancel,
  onCollect,
}: QueueCardProps) {
  const [fileError, setFileError] = useState<string | null>(null);
  const [opening, setOpening] = useState(false);

  // The countdown is to the auto reject, which starts when the order
  // entered the queue. A cash order has no paid_at until it is
  // collected, so it counts down from the reservation time.
  const queuedAt = order.reserved_at ?? order.paid_at;
  const minutesWaiting = queuedAt === null ? 0 : minutesSince(queuedAt, now);
  const minutesLeft = acceptTimeoutMinutes - minutesWaiting;
  const isNew = order.status === "PAID" || order.status === "RESERVED";
  const warning = isNew && minutesLeft <= WARNING_WINDOW_MINUTES;

  const openFile = async () => {
    setFileError(null);
    setOpening(true);
    try {
      const { url } = await getOrderFile(order.id);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (error) {
      setFileError(messageForError(error));
    } finally {
      setOpening(false);
    }
  };

  return (
    <article
      className={
        warning
          ? "flex flex-col gap-3 rounded-lg border-2 border-warning bg-warning-bg p-4"
          : "flex flex-col gap-3 rounded-lg border border-hairline bg-canvas p-4"
      }
    >
      <header className="flex items-baseline justify-between gap-2">
        <h3 className="font-mono text-sm font-medium text-ink">
          #{order.order_no}
        </h3>
        <p className="font-mono text-xs text-steel">
          {formatPaise(order.price_paise)}
        </p>
      </header>

      <p className="text-sm text-ink">
        {order.page_count} page{order.page_count === 1 ? "" : "s"} ×{" "}
        {order.copies} cop{order.copies === 1 ? "y" : "ies"}
      </p>
      <p className="text-xs text-steel">
        {order.paper_size} · {order.color ? "Colour" : "Black and white"} ·{" "}
        {order.duplex ? "Double sided" : "Single sided"}
      </p>

      {order.payment_method === "at_store" && (
        <p className="inline-flex w-fit items-center rounded-full border border-hairline-strong bg-surface px-2 py-0.5 text-xs font-medium text-ink">
          Pay at shop
        </p>
      )}

      {order.reserved_at !== null && (
        <p className="text-xs text-steel">
          Reserved {relativeTime(order.reserved_at, now)}
        </p>
      )}

      {order.paid_at !== null && (
        <p className="text-xs text-steel">
          Paid {relativeTime(order.paid_at, now)}
        </p>
      )}

      {warning && (
        <p className="text-xs font-medium text-warning">
          {minutesLeft > 0
            ? `Auto reject in ${minutesLeft} minute${minutesLeft === 1 ? "" : "s"}`
            : "Past the auto reject limit"}
        </p>
      )}

      {fileError !== null && <Alert>{fileError}</Alert>}

      <div className="flex flex-wrap gap-2">
        <Button
          variant="secondary"
          pending={opening}
          pendingLabel="Opening…"
          onClick={() => void openFile()}
        >
          Open PDF
        </Button>

        {(order.status === "PAID" || order.status === "RESERVED") && (
          <>
            <Button pending={pending} onClick={onAccept}>
              Accept
            </Button>
            <Button variant="secondary" onClick={onReject}>
              Reject
            </Button>
          </>
        )}

        {order.status === "ACCEPTED" && (
          <>
            <Button pending={pending} onClick={onStart}>
              Start printing
            </Button>
            <Button variant="secondary" onClick={onCancel}>
              Cancel
            </Button>
          </>
        )}

        {order.status === "PRINTING" && (
          <Button pending={pending} onClick={onReady}>
            Mark ready
          </Button>
        )}

        {order.status === "READY" && (
          <Button pending={pending} onClick={onCollect}>
            Verify pickup
          </Button>
        )}
      </div>
    </article>
  );
}
