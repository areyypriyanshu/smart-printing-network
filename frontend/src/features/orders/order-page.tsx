import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import {
  getOrder,
  isTerminalStatus,
  statusLabel,
  type OrderDetailResponse,
} from "../../api/orders";
import { Alert, Button } from "../../components/ui";
import { messageForError } from "../../lib/errors";
import { formatPaise } from "../../lib/money";

const POLL_INTERVAL_MS = 5000;

const eventTime = new Intl.DateTimeFormat("en-IN", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Kolkata",
});

export function OrderPage() {
  const { orderId } = useParams<{ orderId: string }>();
  const query = useQuery({
    queryKey: ["orders", orderId],
    queryFn: () => getOrder(orderId as string),
    enabled: orderId !== undefined,
    refetchInterval: (current) =>
      current.state.data !== undefined &&
      isTerminalStatus(current.state.data.order.status)
        ? false
        : POLL_INTERVAL_MS,
  });

  if (query.isPending) {
    return (
      <section className="mx-auto flex w-full max-w-2xl flex-col gap-4 p-6">
        <h1 className="font-display text-2xl font-bold tracking-tight text-ink">
          Order
        </h1>
        <p role="status" className="text-sm text-steel">
          Loading your order…
        </p>
      </section>
    );
  }

  if (query.isError) {
    return (
      <section className="mx-auto flex w-full max-w-2xl flex-col gap-4 p-6">
        <h1 className="font-display text-2xl font-bold tracking-tight text-ink">
          Order
        </h1>
        <Alert>{messageForError(query.error)}</Alert>
        <div>
          <Button variant="secondary" onClick={() => void query.refetch()}>
            Try again
          </Button>
        </div>
      </section>
    );
  }

  return <OrderDetail detail={query.data} />;
}

function OrderDetail({ detail }: { detail: OrderDetailResponse }) {
  const { order, events } = detail;

  return (
    <section className="mx-auto flex w-full max-w-2xl flex-col gap-6 p-6">
      <div className="flex flex-col gap-2">
        <p className="font-mono text-xs uppercase tracking-[0.22em] text-steel">
          Order #{order.order_no}
        </p>
        <h1 className="font-display text-2xl font-bold tracking-tight text-ink">
          {statusLabel(order.status)}
        </h1>
      </div>

      {order.pickup_code !== null && (
        <section
          aria-label="Pickup code"
          className="flex flex-col gap-2 rounded-xl border border-hairline bg-surface p-6"
        >
          <h2 className="font-display text-base font-semibold text-ink">
            Show this code at the counter
          </h2>
          <p className="font-mono text-3xl tracking-[0.3em] text-ink">
            {order.pickup_code}
          </p>
        </section>
      )}

      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
        <dt className="text-steel">Pages</dt>
        <dd className="text-ink">
          {order.page_count} × {order.copies} copies
        </dd>
        <dt className="text-steel">Paper</dt>
        <dd className="text-ink">{order.paper_size}</dd>
        <dt className="text-steel">Colour</dt>
        <dd className="text-ink">
          {order.color ? "Colour" : "Black and white"}
        </dd>
        <dt className="text-steel">Sides</dt>
        <dd className="text-ink">
          {order.duplex ? "Double sided" : "Single sided"}
        </dd>
        <dt className="text-steel">Total</dt>
        <dd className="font-mono text-ink">{formatPaise(order.price_paise)}</dd>
      </dl>

      <section aria-label="History" className="flex flex-col gap-3">
        <h2 className="font-display text-base font-semibold text-ink">
          History
        </h2>
        <ol className="flex flex-col gap-2 border-l border-hairline pl-4">
          {events.map((event) => (
            <li
              key={`${event.at}-${event.to_status}`}
              className="flex flex-col"
            >
              <span className="text-sm text-ink">
                {statusLabel(event.to_status)}
              </span>
              <span className="text-xs text-steel">
                {eventTime.format(new Date(event.at))} IST
              </span>
            </li>
          ))}
        </ol>
      </section>

      <div>
        <Link
          to="/new"
          className="inline-flex min-h-11 items-center rounded-lg border border-hairline-strong bg-canvas px-4 py-2 text-sm font-medium text-ink transition-colors duration-150 hover:bg-surface"
        >
          Start another order
        </Link>
      </div>
    </section>
  );
}
