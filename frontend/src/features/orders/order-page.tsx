import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import {
  getOrder,
  isTerminalStatus,
  orderStatusLabel,
  reorderOrder,
  statusLabel,
  type OrderDetailResponse,
} from "../../api/orders";
import {
  Alert,
  Button,
  buttonClassName,
  sectionTitleClassName,
} from "../../components/ui";
import { messageForError } from "../../lib/errors";
import { formatPaise } from "../../lib/money";
import { pickupShareLink } from "../../lib/share";
import { useShop } from "../shops";
import { ShopWaitEstimate } from "../estimates";

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
  const shop = useShop(order.shop_id);
  const navigate = useNavigate();
  const [reorderError, setReorderError] = useState<string | null>(null);
  const reorder = useMutation({
    mutationFn: () => reorderOrder(order.id),
    onSuccess: (result) => {
      setReorderError(null);
      // The wizard picks the job up from here, with the same options and
      // the same shop already filled in.
      void navigate("/new", {
        state: {
          uploadId: result.upload_id,
          options: {
            paper_size: result.paper_size,
            color: result.color,
            duplex: result.duplex,
            copies: result.copies,
          },
          shopId: result.shop_id,
        },
      });
    },
    onError: (error) => setReorderError(messageForError(error)),
  });

  return (
    <section className="mx-auto flex w-full max-w-2xl flex-col gap-6 p-6">
      <div className="flex flex-col gap-2">
        <p className="font-mono text-xs uppercase tracking-[0.22em] text-steel">
          Order #{order.order_no}
        </p>
        <h1
          // The page polls every five seconds, so the status changes on
          // its own. A live region means a customer is told when the job
          // is ready instead of having to watch the screen.
          aria-live="polite"
          className="font-display text-2xl font-bold tracking-tight text-ink"
        >
          {orderStatusLabel(order)}
        </h1>
      </div>

      {!isTerminalStatus(order.status) && (
        <ShopWaitEstimate shopId={order.shop_id} />
      )}

      {order.pickup_code !== null && (
        <section
          aria-label="Pickup code"
          className="flex flex-col gap-3 rounded-xl border border-hairline bg-surface p-6"
        >
          <h2 className={sectionTitleClassName()}>
            {order.payment_method === "at_store"
              ? `Show this code and pay ${formatPaise(order.price_paise)} in cash`
              : "Show this code at the counter"}
          </h2>
          <p className="font-mono text-3xl tracking-[0.3em] text-ink">
            {order.pickup_code}
          </p>
          <p className="text-sm text-steel">
            Somebody else can collect it for you. Anyone with this code can, so
            send it only to the person you trust.
          </p>
          <div>
            <a
              href={pickupShareLink({
                order_no: order.order_no,
                pickup_code: order.pickup_code,
                shopName: shop.data?.name ?? null,
              })}
              target="_blank"
              rel="noopener noreferrer"
              className={buttonClassName("secondary")}
            >
              Share the code on WhatsApp
            </a>
          </div>
        </section>
      )}

      {shop.data?.phone != null && (
        <p className="text-sm text-steel">
          The shop can be reached on{" "}
          <a
            href={`tel:${shop.data.phone.replace(/[^0-9+]/g, "")}`}
            className="font-medium text-ink underline"
          >
            {shop.data.phone}
          </a>
          .
        </p>
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
        <dd className="font-mono text-base font-medium text-ink">
          {formatPaise(order.price_paise)}
        </dd>
        <dt className="text-steel">Payment</dt>
        <dd className="text-ink">
          {order.payment_method === "at_store"
            ? order.paid_at === null
              ? "Cash at the counter"
              : "Cash paid at the counter"
            : "Paid online"}
        </dd>
      </dl>

      <section aria-label="History" className="flex flex-col gap-3">
        <h2 className={sectionTitleClassName()}>History</h2>
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

      <div className="flex flex-wrap items-center gap-3">
        {detail.file_available ? (
          <Button
            onClick={() => reorder.mutate()}
            pending={reorder.isPending}
            pendingLabel="Preparing…"
          >
            Print this again
          </Button>
        ) : (
          <Link to="/new" className={buttonClassName("secondary")}>
            Upload it again to print it again
          </Link>
        )}
        <Link to="/new" className={buttonClassName("secondary")}>
          Start another order
        </Link>
      </div>
      {reorderError !== null && <Alert>{reorderError}</Alert>}
    </section>
  );
}
