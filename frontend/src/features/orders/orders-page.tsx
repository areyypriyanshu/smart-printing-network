import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { listOrders, orderStatusLabel } from "../../api/orders";
import { Alert, Button, buttonClassName } from "../../components/ui";
import { formatIstDateTime } from "../../lib/dates";
import { messageForError } from "../../lib/errors";
import { formatPaise } from "../../lib/money";

const PAGE_SIZE = 20;

export function OrdersPage() {
  const orders = useQuery({
    queryKey: ["orders", "mine"],
    queryFn: () => listOrders(),
  });

  if (orders.isPending) {
    return (
      <section className="mx-auto flex w-full max-w-2xl flex-col gap-4 p-6">
        <h1 className="font-display text-2xl font-bold tracking-tight text-ink">
          My orders
        </h1>
        <p role="status" className="text-sm text-steel">
          Loading your orders…
        </p>
      </section>
    );
  }

  if (orders.isError) {
    return (
      <section className="mx-auto flex w-full max-w-2xl flex-col gap-4 p-6">
        <h1 className="font-display text-2xl font-bold tracking-tight text-ink">
          My orders
        </h1>
        <Alert>{messageForError(orders.error)}</Alert>
        <div>
          <Button variant="secondary" onClick={() => void orders.refetch()}>
            Try again
          </Button>
        </div>
      </section>
    );
  }

  const { items } = orders.data;

  return (
    <section className="mx-auto flex w-full max-w-2xl flex-col gap-6 p-6">
      <h1 className="font-display text-2xl font-bold tracking-tight text-ink">
        My orders
      </h1>

      {items.length === 0 ? (
        <div className="rounded-lg border border-hairline-soft bg-canvas p-6">
          <p className="text-sm text-ink">You have not placed an order yet.</p>
          <p className="mt-1 text-sm text-steel">
            Upload a PDF and we will show you the price from every verified shop
            near you.
          </p>
          <div className="mt-4">
            <Link to="/new" className={buttonClassName("primary")}>
              Start a new order
            </Link>
          </div>
        </div>
      ) : (
        <ul className="flex flex-col gap-3">
          {items.map((order) => (
            <li key={order.id}>
              <Link
                to={`/orders/${order.id}`}
                className="flex flex-col gap-2 rounded-lg border border-hairline bg-canvas p-4 transition-colors duration-150 hover:border-hairline-strong hover:bg-surface"
              >
                <span className="flex items-baseline justify-between gap-2">
                  <span className="font-mono text-sm font-medium text-ink">
                    #{order.order_no}
                  </span>
                  <span className="font-mono text-xs font-medium text-steel">
                    {formatPaise(order.price_paise)}
                  </span>
                </span>
                <span className="text-sm text-ink">
                  {orderStatusLabel(order)}
                </span>
                {order.payment_method === "at_store" && (
                  <span className="text-xs text-steel">Pay at the counter</span>
                )}
                <span className="text-xs text-steel">
                  {order.page_count} page{order.page_count === 1 ? "" : "s"} ·{" "}
                  {order.copies} cop{order.copies === 1 ? "y" : "ies"} ·{" "}
                  {order.paper_size} ·{" "}
                  {order.color ? "Colour" : "Black and white"}
                </span>
                <span className="text-xs text-steel">
                  Placed {formatIstDateTime(order.created_at)}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {orders.data.next_cursor !== null && (
        <p className="text-xs text-steel">
          Showing the newest {PAGE_SIZE}. Older orders are on the next page.
        </p>
      )}
    </section>
  );
}
