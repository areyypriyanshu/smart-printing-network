import { useEffect, useState } from "react";

import { Alert, Button } from "../../components/ui";
import { messageForError } from "../../lib/errors";
import { useQueue, useVendorAction, type VendorOrder } from "./api";
import { PickupDialog } from "./pickup-dialog";
import { QueueCard } from "./queue-card";
import { ReasonDialog, type ReasonAction } from "./reason-dialog";

// The New column holds both kinds of new job: one that has been paid for
// and one that is reserved to be paid for in cash. They are the same work
// for the shop.
const COLUMNS: { statuses: string[]; title: string }[] = [
  { statuses: ["PAID", "RESERVED"], title: "New" },
  { statuses: ["ACCEPTED"], title: "Accepted" },
  { statuses: ["PRINTING"], title: "Printing" },
  { statuses: ["READY"], title: "Ready" },
];

const CLOCK_INTERVAL_MS = 15_000;

type PendingDialog =
  | { kind: "reason"; action: ReasonAction; order: VendorOrder }
  | { kind: "pickup"; order: VendorOrder }
  | null;

export function VendorQueuePage() {
  const queue = useQueue();
  const action = useVendorAction();
  const [now, setNow] = useState(() => new Date());
  const [dialog, setDialog] = useState<PendingDialog>(null);

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), CLOCK_INTERVAL_MS);
    return () => clearInterval(timer);
  }, []);

  const closeDialog = () => setDialog(null);

  const runAction = (
    order: VendorOrder,
    name: Parameters<typeof action.mutate>[0]["action"],
    body?: { reason?: string; code?: string },
  ) => {
    action.mutate(
      { orderId: order.id, action: name, body },
      // Only close on success. A rejected pickup code or a failed request
      // has to stay on screen, otherwise the shop never sees why it did
      // not work.
      { onSuccess: closeDialog },
    );
  };

  const openDialog = (next: PendingDialog) => {
    // Clear the error from any previous attempt so the dialog does not
    // open showing a stale message.
    action.reset();
    setDialog(next);
  };

  if (queue.isPending) {
    return (
      <section className="mx-auto flex w-full max-w-6xl flex-col gap-4 p-6">
        <h1 className="font-display text-2xl font-bold tracking-tight text-ink">
          Order queue
        </h1>
        <p role="status" className="text-sm text-steel">
          Loading the queue…
        </p>
      </section>
    );
  }

  if (queue.isError) {
    return (
      <section className="mx-auto flex w-full max-w-6xl flex-col gap-4 p-6">
        <h1 className="font-display text-2xl font-bold tracking-tight text-ink">
          Order queue
        </h1>
        <Alert>{messageForError(queue.error)}</Alert>
        <div>
          <Button variant="secondary" onClick={() => void queue.refetch()}>
            Try again
          </Button>
        </div>
      </section>
    );
  }

  const { items, accept_timeout_minutes: acceptTimeoutMinutes } = queue.data;

  // Only the card that the shop is waiting on shows a progress label.
  // The rest of the board is locked while a request is in flight, so two
  // actions cannot be fired at once.
  const pendingOrderId = action.isPending
    ? (action.variables?.orderId ?? null)
    : null;

  return (
    <section className="mx-auto flex w-full max-w-6xl flex-col gap-6 p-6">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="font-display text-2xl font-bold tracking-tight text-ink">
          Order queue
        </h1>
        <p className="text-sm text-steel" aria-live="polite">
          {items.length} active order{items.length === 1 ? "" : "s"}
        </p>
      </div>

      {items.length === 0 ? (
        <div className="rounded-lg border border-hairline-soft bg-canvas p-6">
          <p className="text-sm text-ink">Nothing waiting right now.</p>
          <p className="mt-1 text-sm text-steel">
            New orders appear here as soon as a customer pays or reserves one.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {COLUMNS.map((column) => {
            const columnOrders = items.filter((item) =>
              column.statuses.includes(item.status),
            );
            return (
              <section
                key={column.title}
                aria-label={column.title}
                className="flex flex-col gap-3 rounded-xl border border-hairline bg-surface p-3"
              >
                <h2 className="flex items-center justify-between gap-2 text-sm font-semibold text-ink">
                  {column.title}
                  <span className="rounded-full bg-canvas px-2 py-0.5 font-mono text-xs text-steel">
                    {columnOrders.length}
                  </span>
                </h2>
                {columnOrders.length === 0 ? (
                  <p className="px-1 py-4 text-xs text-steel">Empty</p>
                ) : (
                  <div className="flex flex-col gap-3">
                    {columnOrders.map((order) => (
                      <QueueCard
                        key={order.id}
                        order={order}
                        now={now}
                        acceptTimeoutMinutes={acceptTimeoutMinutes}
                        pendingOrderId={pendingOrderId}
                        onAccept={() => runAction(order, "accept")}
                        onReject={() =>
                          openDialog({
                            kind: "reason",
                            action: "reject",
                            order,
                          })
                        }
                        onStart={() => runAction(order, "start")}
                        onReady={() => runAction(order, "ready")}
                        onCancel={() =>
                          openDialog({
                            kind: "reason",
                            action: "cancel",
                            order,
                          })
                        }
                        onCollect={() => openDialog({ kind: "pickup", order })}
                      />
                    ))}
                  </div>
                )}
              </section>
            );
          })}
        </div>
      )}

      {dialog?.kind === "reason" && (
        <ReasonDialog
          open
          action={dialog.action}
          orderNumber={dialog.order.order_no}
          pending={action.isPending}
          error={action.error}
          onClose={closeDialog}
          onConfirm={(reason) =>
            runAction(dialog.order, dialog.action, { reason })
          }
        />
      )}

      {dialog?.kind === "pickup" && (
        <PickupDialog
          open
          orderNumber={dialog.order.order_no}
          cashAmountPaise={
            dialog.order.payment_method === "at_store"
              ? dialog.order.price_paise
              : null
          }
          pending={action.isPending}
          error={action.error}
          onClose={closeDialog}
          onConfirm={(code) => runAction(dialog.order, "collect", { code })}
        />
      )}
    </section>
  );
}
